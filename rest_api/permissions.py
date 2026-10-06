from rest_framework.permissions import BasePermission
from leadership.access import is_verified
from leadership.capabilities import capabilities_for
class IsVerifiedMember(BasePermission):
 message="Verified KPN membership is required."
 def has_permission(self,request,view): return is_verified(request.user)
class HasCapability(BasePermission):
 message="Your KPN role does not permit this action."
 def has_permission(self,request,view):
  capability=getattr(view,"required_capability",None)
  return bool(capability and capability in capabilities_for(request.user))
def capability_permission(capability):
 class RequiredCapability(HasCapability):
  def has_permission(self,request,view): return capability in capabilities_for(request.user)
 RequiredCapability.__name__=f"Can{capability.title().replace('_','')}"
 return RequiredCapability

def any_capability_permission(*capabilities):
 class AnyCapability(BasePermission):
  message="Your KPN role does not permit this action."
  def has_permission(self,request,view): return bool(set(capabilities).intersection(capabilities_for(request.user)))
 AnyCapability.__name__="CanAny"+"".join(x.title().replace('_','') for x in capabilities)
 return AnyCapability
