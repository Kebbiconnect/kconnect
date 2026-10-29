from django.contrib import admin
from .models import Audit, Control, Delivery, Item, Job, LinkCheck, Source

class ReadOnly(admin.ModelAdmin):
    def has_add_permission(self,request):return False
    def has_change_permission(self,request,obj=None):return False
    def has_delete_permission(self,request,obj=None):return False

# Runtime mutations happen only through the scoped, audited workspace and worker.
for model in [Source,Control,Item,Job,Audit,LinkCheck,Delivery]:admin.site.register(model,ReadOnly)
