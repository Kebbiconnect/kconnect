"""Native equivalent of staff.views.member_mobilization, with mandatory server-side scope.
Allowed titles mirror that view's specific_role_required arguments and the existing
staff decorator's President/Media Director super-access. No capabilities are expanded.
"""
import csv,io
from html import escape
from django.http import HttpResponse
from django.db.models import Q
from rest_framework import generics,permissions,serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.exceptions import NotFound
from leadership.roles import canonical_role_title
from leadership.access import role_title,users_in_jurisdiction
from leadership.models import Zone,LGA,Ward
from staff.models import User
from staff.services.member_admin import members_qs
from .permissions import IsVerifiedMember
from .serializers import MemberSerializer

WEBSITE_MOBILIZATION_ROLES={canonical_role_title(title) for title in ('Director of Membership & Mobilization','Assistant Director of Membership & Mobilization','LGA Community Engagement Officer','President','Senatorial Director','LGA Network Lead','Ward Community Lead','Director of Media & Communications')}
def can_mobilize(user):return bool(getattr(user,'is_authenticated',False) and user.status=='VERIFIED' and role_title(user) in WEBSITE_MOBILIZATION_ROLES)
class CanMobilize(permissions.BasePermission):
    def has_permission(self,request,view):return can_mobilize(request.user)
AUTH=[permissions.IsAuthenticated,IsVerifiedMember,CanMobilize]

def filtered_members(request):
    qs=members_qs(request.user)
    for key in ('zone','lga','ward'):
        value=request.query_params.get(key)
        if value:qs=qs.filter(**{key+'_id':serializers.IntegerField(min_value=1).run_validation(value)})
    for key,choices in [('role',User.ROLE_CHOICES),('tier',User.ROLE_CHOICES),('gender',User.GENDER_CHOICES),('status',User.STATUS_CHOICES)]:
        value=request.query_params.get(key)
        if key=='status':value='VERIFIED' if not value or value=='APPROVED' else value
        if value:qs=qs.filter(**{'role' if key=='tier' else key:serializers.ChoiceField(choices=choices).run_validation(value)})
    query=request.query_params.get('search','').strip()
    if query:qs=qs.filter(Q(first_name__icontains=query)|Q(last_name__icontains=query)|Q(username__icontains=query))
    return qs.order_by('last_name','first_name','id')

class MobilizationListView(generics.ListAPIView):
    serializer_class=MemberSerializer;permission_classes=AUTH
    def get_queryset(self):return User.objects.none() if getattr(self,'swagger_fake_view',False) else filtered_members(self.request)
class MobilizationFiltersView(APIView):
    permission_classes=AUTH
    def get(self,request):
        user=request.user;zones=Zone.objects.all();lgas=LGA.objects.all();wards=Ward.objects.all()
        if user.role=='ZONAL':zones=zones.filter(pk=user.zone_id);lgas=lgas.filter(zone_id=user.zone_id) if user.zone_id else lgas.none();wards=wards.filter(lga__zone_id=user.zone_id) if user.zone_id else wards.none()
        elif user.role=='LGA':lgas=lgas.filter(pk=user.lga_id);zones=zones.filter(pk=user.lga.zone_id) if user.lga_id else zones.none();wards=wards.filter(lga_id=user.lga_id) if user.lga_id else wards.none()
        elif user.role=='WARD':wards=wards.filter(pk=user.ward_id);lgas=lgas.filter(pk=user.ward.lga_id) if user.ward_id else lgas.none();zones=zones.filter(pk=user.ward.lga.zone_id) if user.ward_id else zones.none()
        elif user.role!='STATE':zones=zones.none();lgas=lgas.none();wards=wards.none()
        zone=request.query_params.get('zone');lga=request.query_params.get('lga')
        if zone:lgas=lgas.filter(zone_id=serializers.IntegerField(min_value=1).run_validation(zone))
        if lga:wards=wards.filter(lga_id=serializers.IntegerField(min_value=1).run_validation(lga))
        elif user.role!='WARD':wards=wards.none()  # Choose an LGA before exposing Ward selector options.
        def field(name,label,choices,default=''):
            return {'name':name,'label':label,'type':'choice','required':False,'default_value':default,'choices':[{'value':str(value),'label':str(text)} for value,text in choices]}
        return Response({'fields':[
            field('zone','Zone',[('','All authorized zones')]+list(zones.order_by('name').values_list('id','name'))),
            field('lga','LGA',[('','All authorized LGAs')]+list(lgas.order_by('name').values_list('id','name'))),
            field('ward','Ward' if lga or user.role=='WARD' else 'Ward (choose an LGA first)',[('','All authorized Wards')]+list(wards.order_by('name').values_list('id','name'))),
            field('tier','Membership tier',[('','All tiers')]+list(User.ROLE_CHOICES)),
            field('gender','Gender',[('','All genders')]+list(User.GENDER_CHOICES)),
            field('status','Membership status',User.STATUS_CHOICES,'VERIFIED'),
        ]})

class MobilizationExportView(APIView):
    permission_classes=AUTH
    def get(self,request,format_name):
        headers=['Name','Phone','Position','Zone','LGA','Ward','Gender','Status']
        def rows():
            for member in filtered_members(request).iterator(chunk_size=500):yield [member.get_full_name() or member.username,member.phone,role_title(member) or member.get_role_display(),member.zone.name if member.zone_id else '',member.lga.name if member.lga_id else '',member.ward.name if member.ward_id else '',member.get_gender_display() if member.gender else '',member.get_status_display()]
        if format_name=='csv':
            output=io.StringIO();writer=csv.writer(output);writer.writerow(headers)
            for row in rows():writer.writerow([("'"+str(cell)) if str(cell).lstrip().startswith(('=','+','-','@','\t','\r')) else str(cell) for cell in row])
            response=HttpResponse(output.getvalue().encode('utf-8'),content_type='text/csv; charset=utf-8');response['Content-Disposition']='attachment; filename="kpn_mobilization_contacts.csv"';return response
        if format_name=='pdf':
            from reportlab.lib.pagesizes import A4,landscape
            from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
            from reportlab.lib import colors
            from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,LongTable,TableStyle
            output=io.BytesIO();styles=getSampleStyleSheet();cell_style=ParagraphStyle('ContactCell',fontName='Helvetica',fontSize=10,leading=13)
            elements=[Paragraph('Kebbi Progressive Youth Network',styles['Heading1']),Paragraph('Mobilization contact list',styles['Heading2']),Paragraph('Authorized scope: '+escape(request.user.get_jurisdiction() or request.user.get_role_display()),styles['Normal']),Spacer(1,14)]
            data=[[Paragraph(escape(text),cell_style) for text in headers]]+[[Paragraph(escape(str(cell)),cell_style) for cell in row] for row in rows()]
            table=LongTable(data,colWidths=[140,95,110,85,70,85,55,75],repeatRows=1,hAlign='LEFT');table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#EAF5ED')),('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,0),1,colors.HexColor('#176B36')),('LINEBELOW',(0,1),(-1,-1),.25,colors.HexColor('#DCE3DE')),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]));elements.append(table)
            SimpleDocTemplate(output,pagesize=landscape(A4),leftMargin=28,rightMargin=28,topMargin=28,bottomMargin=28,title='KPN mobilization contacts').build(elements)
            response=HttpResponse(output.getvalue(),content_type='application/pdf');response['Content-Disposition']='attachment; filename="kpn_mobilization_contacts.pdf"';return response
        raise NotFound('Choose csv or pdf.')
