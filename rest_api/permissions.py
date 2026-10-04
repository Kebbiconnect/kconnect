from rest_framework.permissions import BasePermission
from leadership.access import is_verified, role_title
class IsVerifiedMember(BasePermission):
 message='A verified KPN membership is required.'
 def has_permission(self,request,view): return is_verified(request.user)
class HasRoleTitles(BasePermission):
 allowed_titles=()
 def has_permission(self,request,view): return is_verified(request.user) and role_title(request.user) in self.allowed_titles
class IsStateExecutive(IsVerifiedMember):
 def has_permission(self,request,view): return super().has_permission(request,view) and request.user.role=='STATE'
class IsZonalExecutive(IsVerifiedMember):
 def has_permission(self,request,view): return super().has_permission(request,view) and request.user.role=='ZONAL' and bool(request.user.zone_id)
class IsLgaExecutive(IsVerifiedMember):
 def has_permission(self,request,view): return super().has_permission(request,view) and request.user.role=='LGA' and bool(request.user.lga_id)
class IsWardExecutive(IsVerifiedMember):
 def has_permission(self,request,view): return super().has_permission(request,view) and request.user.role=='WARD' and bool(request.user.ward_id)
class IsEditor(HasRoleTitles):
 from leadership.roles import EDITOR_ROLES
 allowed_titles=EDITOR_ROLES
class IsPublicityOfficer(HasRoleTitles):
 from leadership.roles import PUBLICITY_ROLES
 allowed_titles=PUBLICITY_ROLES
class IsEventManager(HasRoleTitles):
 from leadership.roles import EVENT_MANAGER_ROLES
 allowed_titles=EVENT_MANAGER_ROLES
