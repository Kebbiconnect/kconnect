"""Additive native member administration; existing website forms/views remain unchanged."""
from django import forms
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.exceptions import NotFound,ValidationError
from staff.models import User
from staff.forms import EditMemberRoleForm,PromoteMemberForm,DemoteMemberForm,SwapPositionsForm
from leadership.models import RoleDefinition,LGA,Ward
from .permissions import IsVerifiedMember,capability_permission
from .serializers import MemberSerializer

ACTIONS={"edit_role":"Change role / jurisdiction","promote":"Promote member","demote":"Demote member","suspend":"Suspend membership","reinstate":"Reinstate membership","dismiss":"Dismiss member","swap":"Swap leadership positions"}

def assignment(definition,zone,lga,ward):
    """Normalize a seat to the canonical tier and validate parent-child jurisdiction."""
    if definition is None:return {"role":"GENERAL","role_definition":None,"zone":zone,"lga":lga,"ward":ward}
    tier=definition.tier
    if tier=="WARD":
        if not ward:raise ValidationError({"ward":"Ward is required for this position."})
        if lga and ward.lga_id!=lga.pk:raise ValidationError({"ward":"Ward does not belong to the selected LGA."})
        lga=ward.lga
    if tier in {"LGA","WARD"}:
        if not lga:raise ValidationError({"lga":"LGA is required for this position."})
        if zone and lga.zone_id!=zone.pk:raise ValidationError({"lga":"LGA does not belong to the selected zone."})
        zone=lga.zone
    if tier=="ZONAL" and not zone:raise ValidationError({"zone":"Zone is required for this position."})
    return {"role":tier,"role_definition":definition,"zone":None if tier=="STATE" else zone,"lga":lga if tier in {"LGA","WARD"} else None,"ward":ward if tier=="WARD" else None}

def assert_vacant(values,member):
    definition=values["role_definition"]
    if not definition:return
    scope={"role_definition":definition,"status":"VERIFIED"}
    if definition.tier=="ZONAL":scope["zone"]=values["zone"]
    elif definition.tier=="LGA":scope["lga"]=values["lga"]
    elif definition.tier=="WARD":scope["ward"]=values["ward"]
    if User.objects.filter(**scope).exclude(pk=member.pk).exists():raise ValidationError({"role_definition":"This leadership seat is already occupied."})

def optional_pk(values,key):
    value=values.get(key)
    if value in (None,""):return None
    try:return int(value)
    except (ValueError,TypeError):raise ValidationError({key:"Choose a valid location identifier."})

class MemberAdministrationView(APIView):
    permission_classes=[permissions.IsAuthenticated,IsVerifiedMember,capability_permission("STAFF_ADMIN")]
    def get_member(self,pk,lock=False):
        qs=User.objects.select_for_update() if lock else User.objects.all()
        return get_object_or_404(qs,is_superuser=False,pk=pk)
    def form(self,action,member,data=None):
        if action=="edit_role":return EditMemberRoleForm(data,instance=member)
        if action=="promote":return PromoteMemberForm(data,user=member)
        if action=="demote":
            form=DemoteMemberForm(data,user=member)
            tier=(data or {}).get("new_role")
            form.fields["new_role_definition"].queryset=RoleDefinition.objects.filter(tier=tier) if tier in dict(form.fields["new_role"].choices) and tier!="GENERAL" else RoleDefinition.objects.none()
            return form
        if action=="swap":return SwapPositionsForm(data)
        if action in {"suspend","reinstate","dismiss"}:return None
        raise NotFound("Unknown member administration action.")
    def get(self,request,pk):
        member=self.get_member(pk);action=request.query_params.get("action","edit_role")
        form=self.form(action,member);fields=[]
        if form:
            if "zone" in request.query_params and "lga" in form.fields:form.fields["lga"].queryset=LGA.objects.filter(zone_id=optional_pk(request.query_params,"zone"))
            if "lga" in request.query_params and "ward" in form.fields:form.fields["ward"].queryset=Ward.objects.filter(lga_id=optional_pk(request.query_params,"lga"))
            if action=="demote":form.fields["new_role_definition"].queryset=RoleDefinition.objects.filter(tier=request.query_params.get("new_role"))
            for name,field in form.fields.items():
                if name=="member1":continue
                if isinstance(field,forms.ModelChoiceField):
                    qs=field.queryset
                    if qs.model==User:qs=qs.filter(is_superuser=False).exclude(pk=member.pk)
                    choices=[{"value":str(obj.pk),"label":(obj.get_full_name() or obj.username)+" · "+str(obj.role_definition) if isinstance(obj,User) else str(obj)} for obj in qs]
                else:choices=[{"value":str(value),"label":str(label)} for value,label in getattr(field,"choices",[])]
                if not field.required:choices.insert(0,{"value":"","label":"None / General Member" if name=="role_definition" else "Not assigned"})
                initial=form.initial.get(name,getattr(member,name,None));initial=str(initial.pk) if hasattr(initial,"pk") else str(initial) if initial is not None else ""
                fields.append({"name":name,"label":field.label or name.replace("_"," ").title(),"type":"choice" if choices else "text","choices":choices,"default_value":initial,"required":field.required})
        return Response({"member":MemberSerializer(member,context={"request":request}).data,"action":action,"title":ACTIONS[action],"actions":[{"value":k,"label":v} for k,v in ACTIONS.items()],"fields":fields})
    @transaction.atomic
    def post(self,request,pk):
        member=self.get_member(pk,lock=True);action=request.data.get("action");values=dict(request.data)
        # JSON scalars only; this endpoint does not accept file or arbitrary model-field updates.
        if not isinstance(action,str):raise ValidationError({"action":"Choose an administration action."})
        if action in {"suspend","dismiss","reinstate"}:
            if action!="reinstate" and not str(values.get("reason","")).strip():raise ValidationError({"reason":"A reason is required."})
            if action=="suspend":member.status="SUSPENDED"
            elif action=="dismiss":member.status="SUSPENDED";member.is_active=False
            else:
                # Match website reinstatement exactly: it does not reactivate a dismissed account.
                if member.role_definition:
                    RoleDefinition.objects.select_for_update().get(pk=member.role_definition_id)
                    assert_vacant(assignment(member.role_definition,member.zone,member.lga,member.ward),member)
                member.status="VERIFIED";member.approved_by=request.user;member.date_approved=timezone.now()
            member.save()
        elif action=="swap":
            values["member1"]=member.pk;form=SwapPositionsForm(values)
            if not form.is_valid():raise ValidationError(dict(form.errors))
            other=self.get_member(form.cleaned_data["member2"].pk,lock=True)
            keys=("role","role_definition","zone","lga","ward");first={k:getattr(member,k) for k in keys};second={k:getattr(other,k) for k in keys}
            for k in keys:setattr(member,k,second[k]);setattr(other,k,first[k])
            member.save();other.save()
        else:
            form=self.form(action,member,values)
            if not form.is_valid():raise ValidationError(dict(form.errors))
            data=form.cleaned_data
            definition=data.get("role_definition") if action=="edit_role" else data.get("new_role_definition")
            if action=="demote" and data["new_role"]=="GENERAL":definition=None
            if action=="demote" and data["new_role"]!="GENERAL" and not definition:raise ValidationError({"new_role_definition":"Choose a position in the selected tier."})
            # Lock only a validated destination to serialize concurrent API assignments.
            if definition:RoleDefinition.objects.select_for_update().get(pk=definition.pk)
            assigned=assignment(definition,data.get("zone"),data.get("lga"),data.get("ward"));assert_vacant(assigned,member)
            for key,value in assigned.items():setattr(member,key,value)
            member.save()
        return Response(MemberSerializer(member,context={"request":request}).data)

class MemberExportView(APIView):
    permission_classes=[permissions.IsAuthenticated,IsVerifiedMember,capability_permission("EXPORT_MEMBERS")]
    def get(self,request,format_name):
        # Reuse the actual President-only website export functions without changing them.
        from staff.views import export_members_csv,export_members_pdf
        if format_name=="csv":
            import csv,io
            response=export_members_csv(request._request)
            if response.status_code!=200:return response
            rows=csv.reader(io.StringIO(response.content.decode("utf-8")));output=io.StringIO();writer=csv.writer(output)
            for row in rows:writer.writerow([("'"+cell) if cell.lstrip().startswith(("=","+","-","@","\t","\r")) else cell for cell in row])
            response.content=output.getvalue().encode("utf-8")
            return response
        if format_name=="pdf":return export_members_pdf(request._request)
        raise NotFound("Choose csv or pdf.")
