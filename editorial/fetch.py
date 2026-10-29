"""Bounded HTTPS fetching: explicit hosts, public DNS pinned to TLS socket, no proxies.
No cookies, login automation, JavaScript execution or access to private networks.
"""
import http.client
import ipaddress
import socket
import ssl
import time
from html.parser import HTMLParser
from urllib.parse import urlsplit, urlunsplit, urljoin, parse_qsl, urlencode
from urllib.robotparser import RobotFileParser
from django.core.exceptions import ValidationError

MAX_BYTES = 1_000_000
UA = 'KPNEditorialAssistant/1.0'

class FetchError(Exception): pass

def canonical(url):
    p=urlsplit(url.strip())
    if p.scheme!='https' or not p.hostname or p.username or p.password:
        raise FetchError('https_url_required')
    try:
        if p.port not in (None,443): raise FetchError('port_not_allowed')
    except ValueError: raise FetchError('invalid_port')
    host=p.hostname.encode('idna').decode('ascii').lower()
    if any(k.lower() in {'api_key','apikey','access_token','auth_token','password','secret','token'} for k,v in parse_qsl(p.query,keep_blank_values=True)):raise FetchError('credential_query_not_allowed')
    query=urlencode([(k,v) for k,v in parse_qsl(p.query,keep_blank_values=True) if not k.lower().startswith('utm_') and k.lower() not in {'fbclid','gclid'}])
    return urlunsplit(('https',host,p.path or '/',query,''))

def hosts_for(source):
    result={urlsplit(canonical(source.url)).hostname}
    for host in source.allowed_hosts.splitlines():
        host=host.strip().lower()
        if not host: continue
        if any(c in host for c in '/:@*?\\') or not host.isascii(): raise FetchError('invalid_allowed_host')
        result.add(host)
    return result

def public_addresses(host):
    try: records=socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)
    except OSError: raise FetchError('dns_failure')
    ips=list(dict.fromkeys(x[4][0] for x in records))
    if not ips or any(not ipaddress.ip_address(ip).is_global or ipaddress.ip_address(ip).is_multicast for ip in ips): raise FetchError('non_public_address')
    return ips

class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self,host,ip):
        super().__init__(host,timeout=12,context=ssl.create_default_context());self.ip=ip
    def connect(self):
        raw=socket.create_connection((self.ip,443),self.timeout)
        try: self.sock=self._context.wrap_socket(raw,server_hostname=self.host)
        except Exception: raw.close();raise

def fetch(url, allowed_hosts, method='GET'):
    for _ in range(5):
        url=canonical(url);p=urlsplit(url)
        if p.hostname not in allowed_hosts: raise FetchError('host_not_approved')
        ip=public_addresses(p.hostname)[0];conn=PinnedHTTPS(p.hostname,ip)
        try:
            conn.request(method,urlunsplit(('','',p.path,p.query,'')),headers={'User-Agent':UA,'Accept':'text/html,application/rss+xml,application/atom+xml,application/xml,text/plain;q=0.9','Accept-Encoding':'identity'})
            response=conn.getresponse();status=response.status
            if status in {301,302,303,307,308}:
                location=response.getheader('Location')
                if not location: raise FetchError('redirect_missing_location')
                url=urljoin(url,location);continue
            chunks=[];size=0;deadline=time.monotonic()+20
            if method=='GET':
                while True:
                    if time.monotonic()>deadline:raise FetchError('response_timeout')
                    chunk=response.read1(min(65536,MAX_BYTES+1-size))
                    if not chunk:break
                    chunks.append(chunk);size+=len(chunk)
                    if size>MAX_BYTES:raise FetchError('response_too_large')
            data=b''.join(chunks)
            if len(data)>MAX_BYTES: raise FetchError('response_too_large')
            if 'gzip' in (response.getheader('Content-Encoding') or '').lower(): raise FetchError('unsupported_encoding')
            return status,data,url
        except (OSError,http.client.HTTPException): raise FetchError('network_failure')
        finally: conn.close()
    raise FetchError('too_many_redirects')

def permitted_fetch(url,allowed_hosts):
    p=urlsplit(canonical(url));robots=f'https://{p.hostname}/robots.txt'
    status,body,_=fetch(robots,allowed_hosts)
    if status in {401,403,429} or status>=500: raise FetchError('robots_unavailable')
    if status==200:
        parser=RobotFileParser();parser.parse(body.decode('utf-8',errors='replace').splitlines())
        if not parser.can_fetch(UA,url): raise FetchError('robots_disallow')
    status,body,final=fetch(url,allowed_hosts)
    if status!=200: raise FetchError(f'http_{status}')
    return body,final

class Readable(HTMLParser):
    def __init__(self): super().__init__(convert_charrefs=True);self.skip=0;self.parts=[];self.links=[];self.current_link=None
    def handle_starttag(self,tag,attrs):
        if tag in {'script','style','nav','footer','header','form'}: self.skip+=1
        if not self.skip and tag=='a':
            href=dict(attrs).get('href','')
            self.current_link={'url':href,'label':''};self.links.append(self.current_link)
        if not self.skip and tag in {'p','div','br','li','h1','h2','h3','article'}: self.parts.append('\n')
    def handle_endtag(self,tag):
        if tag=='a':self.current_link=None
        if tag in {'script','style','nav','footer','header','form'}: self.skip=max(0,self.skip-1)
    def handle_data(self,data):
        if not self.skip:
            self.parts.append(data)
            if self.current_link is not None:self.current_link['label']+=data

def readable(body):
    parser=Readable();parser.feed(body.decode('utf-8',errors='replace'))
    return '\n'.join(' '.join(x.split()) for x in ''.join(parser.parts).splitlines() if x.strip())[:24000]


def application_links(body,base):
    parser=Readable();parser.feed(body.decode('utf-8',errors='replace'));result=[]
    for link in parser.links[:100]:
        try:url=canonical(urljoin(base,link['url']))
        except (FetchError,ValueError):continue
        label=' '.join(link['label'].split())[:160]
        if any(word in (label+' '+url).casefold() for word in ('apply','application','recruit','career','scholarship','vacanc','job','portal')):
            result.append({'url':url,'label':label})
        if len(result)>=15:break
    return result
