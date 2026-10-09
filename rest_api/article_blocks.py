"""Validate native Editor.js writes without changing existing website views or stored articles."""
import copy,json
from urllib.parse import urlsplit
import bleach
from rest_framework import serializers

INLINE_TAGS=('b','strong','i','em','u','a','code','br','mark')
def inline_text(value):
    if not isinstance(value,str):raise serializers.ValidationError({'content_json':'Article text and captions must be strings.'})
    return bleach.clean(value,tags=INLINE_TAGS,attributes={'a':['href','title']},protocols=['http','https','mailto','tel'],strip=True)
def safe_media_url(value):
    if not isinstance(value,str):raise serializers.ValidationError({'content_json':'Media URLs must be strings.'})
    if "\\" in value or any(ord(char)<32 or ord(char)==127 for char in value):
        raise serializers.ValidationError({'content_json':'Media URLs must not contain backslashes or control characters.'})
    value=value.strip()
    if not value:return value
    try:parsed=urlsplit(value)
    except ValueError:raise serializers.ValidationError({"content_json":"Invalid media URL."})
    if (parsed.scheme in ('https','http') and parsed.hostname and not parsed.username) or (not parsed.scheme and not parsed.netloc and value.startswith('/') and not value.startswith('//')):return value
    raise serializers.ValidationError({'content_json':'Use HTTP/HTTPS media URLs or same-site media paths.'})
def sanitize_article_blocks(value):
    legacy=isinstance(value,str)
    if legacy:
        try:value=json.loads(value)
        except (ValueError,TypeError):return value  # Existing website fallback safely escapes a non-JSON string.
    if value is None:return None
    if not isinstance(value,dict) or not isinstance(value.get('blocks',[]),list):raise serializers.ValidationError({'content_json':'Use an Editor.js object containing a blocks list.'})
    result=copy.deepcopy(value)
    def items(rows,depth=0):
        if not isinstance(rows,list) or depth>20:raise serializers.ValidationError({'content_json':'Invalid or excessively nested article list.'})
        for i,item in enumerate(rows):
            if isinstance(item,str):rows[i]=inline_text(item)
            elif isinstance(item,dict):
                for key in ('text','content'):
                    if key in item:item[key]=inline_text(item[key])
                if 'items' in item:items(item['items'],depth+1)
            else:raise serializers.ValidationError({'content_json':'List items must be text or structured items.'})
    for block in result.get('blocks',[]):
        if not isinstance(block,dict) or not isinstance(block.get('data'),dict):raise serializers.ValidationError({'content_json':'Each article block requires a data object.'})
        data=block['data'];kind=block.get('type')
        for key in ('text','caption','title','message'):
            if key in data:data[key]=inline_text(data[key])
        if kind=='header':
            try:level=int(data.get('level',2))
            except (ValueError,TypeError):raise serializers.ValidationError({'content_json':'Heading level must be 2, 3 or 4.'})
            if level not in (2,3,4):raise serializers.ValidationError({'content_json':'Heading level must be 2, 3 or 4.'})
            data['level']=level
        if kind in ('list','checklist'):items(data.get('items',[]))
        if kind=='image':
            if 'file' in data:
                if not isinstance(data['file'],dict):raise serializers.ValidationError({'content_json':'Image file data must be an object.'})
                if 'url' in data['file']:data['file']['url']=safe_media_url(data['file']['url'])
            if 'url' in data:data['url']=safe_media_url(data['url'])
        if kind=='embed' and 'embed' in data:data['embed']=safe_media_url(data['embed'])
    return json.dumps(result) if legacy else result
