"""Role-aware capabilities shared by web and API authorization."""
from .access import can_approve_members,is_verified,role_title
ALL_CAPABILITIES=("VIEW_MEMBERS","REVIEW_APPLICANTS","SUBMIT_REPORTS","REVIEW_REPORTS","OVERSIGHT_REPORTS","WRITE_ARTICLES","REVIEW_ARTICLES","ALL_ARTICLES","UPLOAD_MEDIA","REVIEW_MEDIA","MANAGE_HUBS","MANAGE_PATRONS","MANAGE_REPORTERS","REVIEW_COMMUNITY_REPORTS","SUBMIT_COMMUNITY_REPORT","CREATE_ANNOUNCEMENT","VIEW_EVENTS","MANAGE_EVENTS","RECORD_ATTENDANCE","EDIT_MINUTES","MANAGE_PROGRAMS_WOMEN","MANAGE_PROGRAMS_YOUTH","MANAGE_PROGRAMS_WELFARE","MANAGE_PROGRAM_PARTICIPANTS","VIEW_FINANCE","RECORD_DONATION","VERIFY_DONATION","RECORD_EXPENSE","MANAGE_FINANCIAL_REPORTS","MANAGE_AUDIT_REPORTS","VIEW_AUDIT_REPORTS","LEGAL_REVIEW","VIEW_DISCIPLINE","CREATE_DISCIPLINE","DECIDE_DISCIPLINE","STAFF_VIEW","STAFF_ADMIN","EXPORT_MEMBERS","MANAGE_FAQ","MANAGE_OUTREACH","VIEW_WARD_MEETINGS","MANAGE_WARD_MEETINGS","MANAGE_WARD_ATTENDANCE","VIEW_OVERSIGHT","MOBILIZATION")
def capabilities_for(user):
 if not is_verified(user): return ()
 title,tier=role_title(user),user.role; caps={"VIEW_EVENTS"}
 if tier in {"STATE","ZONAL","LGA","WARD"}: caps|={"VIEW_MEMBERS","WRITE_ARTICLES","SUBMIT_COMMUNITY_REPORT","CREATE_ANNOUNCEMENT","VIEW_WARD_MEETINGS"}
 if can_approve_members(user): caps.add("REVIEW_APPLICANTS")
 if tier in {"ZONAL","LGA","WARD"}: caps.add("SUBMIT_REPORTS")
 if tier in {"ZONAL","LGA"}: caps.add("REVIEW_REPORTS")
 if title in {"President","Director of Monitoring & Compliance"}: caps|={"REVIEW_REPORTS","OVERSIGHT_REPORTS"}
 if title in {"Director of Media & Communications","Assistant Director of Media & Communications"}: caps|={"REVIEW_ARTICLES","ALL_ARTICLES"}
 if title in {"Director of Media & Communications","Assistant Director of Media & Communications","Senatorial Communications Officer","LGA Communications Officer","Ward Communications Officer"}: caps.add("UPLOAD_MEDIA")
 if title=="Director of Media & Communications": caps|={"REVIEW_MEDIA","MANAGE_HUBS","MANAGE_PATRONS","MANAGE_REPORTERS","REVIEW_COMMUNITY_REPORTS"}
 if title=="President": caps|={"MANAGE_HUBS","MANAGE_PATRONS","MANAGE_REPORTERS","REVIEW_COMMUNITY_REPORTS","VIEW_AUDIT_REPORTS","DECIDE_DISCIPLINE","STAFF_ADMIN","EXPORT_MEMBERS","VIEW_OVERSIGHT"}
 if title in {"Director of Programmes & Events","Assistant Director of Programmes & Events"}: caps|={"MANAGE_EVENTS","RECORD_ATTENDANCE"}
 if title=="General Secretary": caps.add("EDIT_MINUTES")
 if title in {"Director of Women's Development","Assistant Director of Women's Development","LGA Women's Development Officer"}: caps|={"MANAGE_PROGRAMS_WOMEN","MANAGE_PROGRAM_PARTICIPANTS"}
 if title=="Director of Youth Development": caps|={"MANAGE_PROGRAMS_YOUTH","MANAGE_PROGRAM_PARTICIPANTS"}
 if title in {"Director of Member Support & Welfare","LGA Member Support Officer","Ward Community Support Officer"}: caps|={"MANAGE_PROGRAMS_WELFARE","MANAGE_PROGRAM_PARTICIPANTS"}
 if title in {"President","Director of Finance","Finance Operations Officer","Director of Audit & Accountability"}: caps.add("VIEW_FINANCE")
 if title=="Director of Finance": caps|={"RECORD_DONATION","VERIFY_DONATION"}
 if title=="Finance Operations Officer": caps|={"RECORD_EXPENSE","MANAGE_FINANCIAL_REPORTS"}
 if title=="Director of Audit & Accountability": caps.add("MANAGE_AUDIT_REPORTS")
 if tier=="STATE": caps|={"VIEW_DISCIPLINE","CREATE_DISCIPLINE","STAFF_VIEW"}
 if title=="Director of Legal Affairs & Ethics": caps.add("LEGAL_REVIEW")
 if title=="Assistant General Secretary": caps.add("MANAGE_FAQ")
 if title=="Director of Public Relations & Partnerships": caps.add("MANAGE_OUTREACH")
 if title in {"Ward Community Lead","Ward Administrative Officer"}: caps|={"MANAGE_WARD_MEETINGS","MANAGE_WARD_ATTENDANCE"}
 if title in {"President","Director of Community Engagement","Assistant Director of Community Engagement"}: caps.add("MOBILIZATION")
 return tuple(cap for cap in ALL_CAPABILITIES if cap in caps)
