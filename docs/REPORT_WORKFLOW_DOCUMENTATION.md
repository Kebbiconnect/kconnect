# KPN Platform - Hierarchical Report Workflow Documentation
## Complete End-to-End Report Submission and Review System

**Date:** October 13, 2025  
**Version:** 2.0 (Fully Functional)  
**Status:** ✅ COMPLETE

---

## 🎯 OVERVIEW

The KPN Platform now has a **fully functional hierarchical reporting system** that automatically escalates reports through the organizational chain:

**Ward → LGA → Zonal → State**

This document provides complete details on how the system works, from submission to final review.

---

## 📊 SYSTEM ARCHITECTURE

### **1. Report Model Enhancements**

#### **New Fields Added:**
```python
parent_report = ForeignKey('self')         # Links to parent report in the chain
is_escalated = BooleanField()              # Tracks if report was escalated
escalated_at = DateTimeField()             # When escalation occurred
```

#### **New Status:**
- `ESCALATED` - Report approved and escalated to next level

#### **Helper Methods:**
- `get_report_chain()` - Returns full chain from root to current report
- `can_be_escalated()` - Checks if report is eligible for escalation

---

## 🔄 COMPLETE WORKFLOW

### **Step 1: Ward Secretary Submits Report**

**Who:** Ward Secretary (or any Ward leader with `role='WARD'`)  
**To:** LGA Coordinator

**Process:**
1. Ward leader logs in and navigates to "Submit Report"
2. Fills out the report form:
   - Title (e.g., "Ward Weekly Report - Week 1")
   - Period (e.g., "January 2025", "Week 1")
   - Content (detailed report text)
   - Deadline (optional)
3. Clicks "Submit Report"

**What Happens:**
```python
# System automatically:
- Identifies the LGA Coordinator for the Ward's LGA
- Creates report with report_type='WARD_TO_LGA'
- Sets status='SUBMITTED'
- Records submitted_at timestamp
- Sets submitted_to=LGA_Coordinator
- Sends email notification to LGA Coordinator
```

**Notification Sent To:** LGA Coordinator
- Subject: "New Report Submitted: [Title]"
- Contains: Title, Period, Submitted by, Deadline

---

### **Step 2: LGA Coordinator Reviews Ward Report**

**Who:** LGA Coordinator  
**Action:** Reviews the Ward report

**Process:**
1. LGA Coordinator receives email notification
2. Logs in to dashboard
3. Navigates to "View Reports"
4. Sees report in "Pending" tab (filter_status=pending)
5. Clicks on report to review
6. Reviews content and makes decision:
   - **APPROVE** → Escalates to Zonal
   - **FLAG** → Marks for issues, sends back to Ward
   - **REJECT** → Rejects report

**Dashboard Statistics Shown:**
- Pending Reports: Count of unreviewed reports
- Reviewed Reports: Count of reviewed reports
- Approved: Count of approved reports
- Flagged: Count of flagged reports
- Rejected: Count of rejected reports
- Escalated: Count of escalated reports
- Overdue: Count of overdue reports

---

### **Step 3A: LGA Coordinator APPROVES (Automatic Escalation)**

**What Happens When APPROVED:**
```python
# System automatically:
1. Marks Ward report as status='ESCALATED'
2. Sets is_escalated=True
3. Records escalated_at timestamp

4. Creates NEW report:
   - title = "Consolidated Ward to LGA Report - [period]"
   - report_type = 'LGA_TO_ZONAL'
   - content = "[Escalated from LGA Coordinator]\n\n[original content]"
   - submitted_by = LGA_Coordinator
   - submitted_to = Zonal_Coordinator
   - parent_report = original_Ward_report
   - status = 'SUBMITTED'
   - submitted_at = now()

5. Sends two notifications:
   - To Ward Secretary: "Report APPROVED"
   - To Zonal Coordinator: "New Report Submitted"
```

**Success Message Shown:**
> "Report approved and escalated to [Zonal Coordinator Name]!"

---

### **Step 3B: LGA Coordinator FLAGS or REJECTS**

**What Happens When FLAGGED:**
```python
# System:
- Sets status='FLAGGED'
- Saves review_notes
- Sends notification to Ward Secretary
- Does NOT escalate
```

**Notification to Ward Secretary:**
- Subject: "Report FLAGGED: [Title]"
- Contains: Status, Reviewed by, Review notes

**What Happens When REJECTED:**
```python
# System:
- Sets status='REJECTED'
- Saves review_notes
- Sends notification to Ward Secretary
- Does NOT escalate
```

---

### **Step 4: Zonal Coordinator Reviews LGA Report**

**Who:** Zonal Coordinator  
**Action:** Reviews the escalated LGA report

**Process:**
1. Zonal Coordinator receives email notification
2. Logs in to dashboard
3. Sees the escalated report from LGA
4. Reviews report content (includes original Ward report)
5. Makes decision:
   - **APPROVE** → Escalates to State Supervisor
   - **FLAG** → Marks for issues, sends back to LGA
   - **REJECT** → Rejects report

**Report Content Shows:**
```
[Escalated from John Doe - LGA Coordinator]

[Original Ward report content here]
```

**Parent Report Link:**
The system tracks that this LGA report came from the Ward report via `parent_report` field.

---

### **Step 5: Zonal Coordinator APPROVES (Final Escalation)**

**What Happens When APPROVED:**
```python
# System automatically:
1. Marks LGA report as status='ESCALATED'
2. Sets is_escalated=True
3. Records escalated_at timestamp

4. Creates NEW report:
   - title = "Consolidated LGA to Zonal Report - [period]"
   - report_type = 'ZONAL_TO_STATE'
   - content = "[Escalated from Zonal Coordinator]\n\n[LGA report content]"
   - submitted_by = Zonal_Coordinator
   - submitted_to = State_Supervisor
   - parent_report = LGA_report
   - status = 'SUBMITTED'
   - submitted_at = now()

5. Sends notifications:
   - To LGA Coordinator: "Report APPROVED"
   - To State Supervisor: "New Report Submitted"
```

---

### **Step 6: State Supervisor Final Review**

**Who:** State Supervisor (or President)  
**Action:** Final review of the report chain

**Process:**
1. State Supervisor receives email notification
2. Logs in to dashboard
3. Reviews the Zonal report
4. Can see the full report chain:
   - Original Ward report
   - LGA escalation
   - Zonal escalation
   - Current State report
5. Makes final decision:
   - **APPROVE** → Marks as approved (NO further escalation)
   - **FLAG** → Marks for issues
   - **REJECT** → Rejects report

**What Happens When APPROVED:**
```python
# System:
- Sets status='APPROVED'
- Sets is_reviewed=True
- Records reviewed_by=State_Supervisor
- Records reviewed_at timestamp
- Sends notification to Zonal Coordinator
- Does NOT escalate (end of chain)
```

**Special Note:** ZONAL_TO_STATE reports do NOT escalate further.

---

## 📧 NOTIFICATION SYSTEM

### **Notification Triggers:**

#### **1. Report Submitted:**
- **Sent To:** Supervisor (submitted_to)
- **Subject:** "New Report Submitted: [Title]"
- **Content:**
  ```
  Dear [Supervisor Name],
  
  A new report has been submitted for your review:
  
  Title: [Report Title]
  Period: [Period]
  Submitted by: [Name]
  Report Type: [Type]
  Deadline: [Deadline]
  
  Please log in to the KPN platform to review this report.
  ```

#### **2. Report Reviewed:**
- **Sent To:** Submitter (submitted_by)
- **Subject:** "Report [STATUS]: [Title]"
- **Content:**
  ```
  Dear [Submitter Name],
  
  Your report has been reviewed:
  
  Title: [Report Title]
  Status: [APPROVED/FLAGGED/REJECTED/ESCALATED]
  Reviewed by: [Reviewer Name]
  Review Notes: [Notes]
  
  Please log in to the KPN platform to view the full details.
  ```

#### **3. Report Escalated:**
- **Sent To:** Next supervisor in chain
- **Subject:** "New Report Submitted: Consolidated [Type] - [Period]"
- **Content:** Same as "Report Submitted" format

---

## 🔍 DASHBOARD FEATURES

### **View Reports Dashboard**

**URL:** `/staff/view-reports/`  
**Access:** All approved leaders (Ward, LGA, Zonal, State)

#### **Dashboard Statistics:**
```python
- Total Reports: All reports submitted to user
- Pending: Reports awaiting review (status=SUBMITTED, is_reviewed=False)
- Reviewed: All reviewed reports
- Approved: Reports approved
- Flagged: Reports flagged for issues
- Rejected: Reports rejected
- Escalated: Reports escalated to next level
- Overdue: Reports past deadline
```

#### **Filter Options:**
- `?status=all` - Show all reports
- `?status=pending` - Show only pending reports
- `?status=reviewed` - Show only reviewed reports
- `?status=approved` - Show only approved reports
- `?status=flagged` - Show only flagged reports
- `?status=rejected` - Show only rejected reports
- `?status=escalated` - Show only escalated reports
- `?status=overdue` - Show only overdue reports

#### **View Logic:**
```python
# Regular leaders see only reports submitted TO them
reports = Report.objects.filter(submitted_to=current_user)

# President and State Supervisor see ALL reports
if is_president or is_state_supervisor:
    reports = Report.objects.all()
```

---

## 🔗 REPORT CHAIN TRACKING

### **Parent-Child Relationships:**

Each escalated report maintains a link to its parent:

```python
Ward Report (ID: 1)
  ↓ parent_report=1
LGA Report (ID: 2)  
  ↓ parent_report=2
Zonal Report (ID: 3)
  ↓ (Final review, no child)
State Review
```

### **Get Full Chain:**
```python
# From any report, get full chain:
report.get_report_chain()
# Returns: [Ward_Report, LGA_Report, Zonal_Report]
```

---

## ✅ VALIDATION RULES

### **Report Escalation Rules:**

1. **Can Escalate IF:**
   - Status = 'APPROVED'
   - is_escalated = False
   - report_type in ['WARD_TO_LGA', 'LGA_TO_ZONAL']

2. **Cannot Escalate IF:**
   - Status ≠ 'APPROVED'
   - Already escalated (is_escalated=True)
   - report_type = 'ZONAL_TO_STATE' (end of chain)

### **Supervisor Identification:**

```python
# Ward → LGA:
LGA_Coordinator = User.objects.filter(
    role='LGA',
    lga=ward_user.lga,
    role_definition__title='LGA Coordinator',
    status='APPROVED'
).first()

# LGA → Zonal:
Zonal_Coordinator = User.objects.filter(
    role='ZONAL',
    zone=lga_user.zone,
    role_definition__title='Zonal Coordinator',
    status='APPROVED'
).first()

# Zonal → State:
State_Supervisor = User.objects.filter(
    role='STATE',
    role_definition__title='State Supervisor',
    status='APPROVED'
).first()
```

---

## 🚀 TESTING THE WORKFLOW

### **Test Scenario:**

#### **Setup:**
1. Create test users:
   - Ward Secretary (Ward A, LGA X, Zone 1)
   - LGA Coordinator (LGA X, Zone 1)
   - Zonal Coordinator (Zone 1)
   - State Supervisor (State)

#### **Test Steps:**

**Step 1: Ward Submission**
```
1. Log in as Ward Secretary
2. Navigate to Submit Report
3. Fill form:
   - Title: "Ward A Weekly Report - Week 1"
   - Period: "January 2025"
   - Content: "Ward activities summary..."
   - Deadline: [future date]
4. Submit
5. ✅ Verify: LGA Coordinator receives email
```

**Step 2: LGA Review**
```
1. Log in as LGA Coordinator
2. Navigate to View Reports
3. ✅ Verify: Pending count = 1
4. Click on report
5. Review and approve
6. ✅ Verify: 
   - Success message shows "escalated to [Zonal Coordinator]"
   - Ward Secretary receives "APPROVED" email
   - Zonal Coordinator receives "New Report" email
```

**Step 3: Zonal Review**
```
1. Log in as Zonal Coordinator
2. Navigate to View Reports
3. ✅ Verify: Pending count = 1
4. ✅ Verify: Report shows "[Escalated from LGA Coordinator]"
5. Review and approve
6. ✅ Verify:
   - Success message shows "escalated to [State Supervisor]"
   - LGA Coordinator receives "APPROVED" email
   - State Supervisor receives "New Report" email
```

**Step 4: State Review**
```
1. Log in as State Supervisor
2. Navigate to View Reports
3. ✅ Verify: Pending count = 1
4. ✅ Verify: Report shows full chain
5. Review and approve
6. ✅ Verify:
   - Success message shows "approved successfully"
   - NO escalation (end of chain)
   - Zonal Coordinator receives "APPROVED" email
```

---

## 📊 REPORT STATUSES

| Status | Description | Can Escalate? | Next Action |
|--------|-------------|---------------|-------------|
| **DRAFT** | Report created but not submitted | No | Submit |
| **SUBMITTED** | Awaiting supervisor review | No | Review |
| **UNDER_REVIEW** | Being reviewed | No | Complete review |
| **APPROVED** | Approved by supervisor | Yes (Ward, LGA only) | Auto-escalate or end |
| **FLAGGED** | Issues identified | No | Address issues |
| **REJECTED** | Rejected by supervisor | No | Revise and resubmit |
| **ESCALATED** | Escalated to next level | No | Monitor child report |

---

## 🔧 TECHNICAL IMPLEMENTATION

### **Key Functions:**

#### **1. submit_report (core/views.py)**
```python
- Identifies correct supervisor based on submitter role
- Creates report with proper report_type
- Sets status='SUBMITTED'
- Sends notification to supervisor
```

#### **2. review_report (core/views.py)**
```python
- Validates reviewer permission
- Updates report status based on action
- If APPROVED and can_be_escalated:
  - Calls _escalate_report()
  - Sends notifications
```

#### **3. _escalate_report (core/views.py)**
```python
- Determines next supervisor in chain
- Creates new report at next level
- Links via parent_report
- Marks original as ESCALATED
- Returns new report
```

#### **4. _send_report_notification (core/views.py)**
```python
- Handles email notifications
- Two types: 'submitted' and 'reviewed'
- Uses Django send_mail with fail_silently=True
```

#### **5. view_reports (staff/views.py)**
```python
- Filters reports by submitted_to (or all for President/State Supervisor)
- Provides comprehensive statistics
- Supports status filtering
- Optimized with select_related()
```

---

## 🎯 SUCCESS CRITERIA

### **Workflow is Successful IF:**

✅ **1. Proper Routing:**
- Ward reports go to correct LGA Coordinator
- LGA reports go to correct Zonal Coordinator
- Zonal reports go to State Supervisor

✅ **2. Automatic Escalation:**
- APPROVED Ward reports auto-create LGA reports
- APPROVED LGA reports auto-create Zonal reports
- APPROVED Zonal reports do NOT escalate

✅ **3. Notifications:**
- Supervisors notified on submission
- Submitters notified on review
- Escalation triggers new submission notification

✅ **4. Dashboard Accuracy:**
- Pending count reflects unreviewed reports
- Statistics are accurate
- Filters work correctly

✅ **5. Chain Tracking:**
- parent_report links maintained
- get_report_chain() returns full path
- No orphaned reports

---

## 📝 FUTURE ENHANCEMENTS

### **Potential Improvements:**

1. **Report Templates**
   - Predefined templates for common reports
   - Structured fields (instead of just text)

2. **Batch Processing**
   - Consolidate multiple Ward reports into one LGA report
   - Aggregate statistics automatically

3. **Report Analytics**
   - Submission trends
   - Average review time
   - Compliance rates

4. **Reminder System**
   - Auto-remind supervisors of pending reports
   - Alert on approaching deadlines
   - Weekly digest emails

5. **Report Versioning**
   - Track edits and revisions
   - Compare versions
   - Audit trail

6. **Advanced Permissions**
   - Deputy reviewers
   - Delegation of review authority
   - Emergency escalation override

---

## 🛠️ TROUBLESHOOTING

### **Common Issues:**

#### **Issue 1: Supervisor Not Found**
**Symptom:** Error message "No supervisor found to submit the report to"  
**Cause:** No approved LGA/Zonal/State coordinator exists  
**Solution:** Ensure all coordinator positions are filled with APPROVED users

#### **Issue 2: Notifications Not Sending**
**Symptom:** No emails received  
**Cause:** Email not configured or user has no email  
**Solution:** Check Django email settings, verify user emails

#### **Issue 3: Report Not Escalating**
**Symptom:** APPROVED but not escalated  
**Cause:** State-level report (ZONAL_TO_STATE)  
**Solution:** This is expected - State reports are final

#### **Issue 4: Wrong Supervisor**
**Symptom:** Report goes to wrong person  
**Cause:** User's zone/LGA mismatch  
**Solution:** Verify user's zone/LGA assignments match their jurisdiction

---

## 📞 SUPPORT

**For Technical Issues:**
- Check Django logs
- Verify user roles and permissions
- Test with debug mode on

**For Workflow Questions:**
- Refer to this documentation
- Contact system administrator

---

## ✅ WORKFLOW CHECKLIST

### **Pre-Launch Checklist:**

- [x] Report model with parent_report field
- [x] Report escalation logic
- [x] Notification system
- [x] Dashboard statistics
- [x] View reports filtering
- [x] Permission checks
- [x] Email configuration
- [ ] End-to-end testing completed
- [ ] User training documentation
- [ ] Production deployment

---

**Document Status:** ✅ COMPLETE  
**Last Updated:** October 13, 2025  
**Version:** 2.0  
**Maintained By:** Development Team

---

**END OF DOCUMENTATION**
