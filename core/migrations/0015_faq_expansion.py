"""Owner-directed FAQ expansion (2026-11-27): seed the 21 new FAQs.

Adds the questions/cards 10-30 introduced in
``core/templates/core/faq.html`` (see ``core/faq_categories.py`` for
the matching category mapping). Idempotent: ``get_or_create`` keyed
by question, so rows staff already added by hand are left untouched.
Reverse deletes exactly the rows whose question is in the new list.
"""

from django.db import migrations

# (question, answer, order) — order runs 10..30, matching the
# template card indices (openFaq 10-30).
NEW_FAQS = [
    ('When was KPN founded, and is it registered?',
     'KPN was founded on 30 May 2023. It is registered with the Corporate Affairs Commission (CAC) of Nigeria as Incorporated Trustees, so it operates as a recognised non-profit organisation.',
     10),
    ('Which areas does KPN cover?',
     'KPN operates across all 21 local government areas and 225 wards of Kebbi State, with leadership and member teams at state, senatorial zone, LGA and ward levels.',
     11),
    ("What does 'One Voice, One Change' mean?",
     "'One Voice, One Change' is the motto of KPN. It expresses the idea behind the network: young people across Kebbi State speaking together, with one voice, to bring positive change to their communities.",
     12),
    ('How do I join KPN?',
     'You can join on the KPN website or in the KPN mobile app. Create an account, complete your profile, and choose your ward and LGA. Your application is reviewed by KPN leaders, and you will be notified when it is approved.',
     13),
    ('What happens after I submit my membership application?',
     'Your application shows as pending while it is reviewed by the leaders responsible for your area. Once it is approved, your account becomes fully active and you can take part in KPN activities and use member features on the website and in the app.',
     14),
    ('How do I sign in to the KPN mobile app?',
     'The app uses the same account as the KPN website. Sign in with the username or email address and password you registered with on kpn.com.ng. If you do not have an account yet, you can create one from the app.',
     15),
    ('Who leads KPN in my ward or LGA?',
     'Every ward and LGA in Kebbi State has its own KPN leadership team. You can see the current office holders for your area in the Leadership Directory on the website and in the app.',
     16),
    ('What are the senatorial zones in KPN?',
     'For coordination, KPN groups the 21 LGAs into three senatorial zones: Kebbi North, Kebbi Central and Kebbi South. Each zone has its own leadership team supporting the LGA and ward teams.',
     17),
    ('How do I report a problem or a story from my community?',
     "Use the community report form on the website or in the app (Report a Concern). Describe what happened, where and when, and add photos or other evidence if you have them. Reports are reviewed and verified before anything is published, and a reporter's name and phone number are never published.",
     18),
    ('What kind of issues can I report?',
     "You can report community needs, abandoned or delayed public projects, positive developments, and anything else affecting your community's welfare or safety. Reports help KPN follow up issues and recognise progress.",
     19),
    ('What is the Opportunities Hub?',
     'The Opportunities Hub on the KPN website and app collects scholarships, grants, jobs, internships, trainings and fellowships that are open to young people in Kebbi State and Nigeria. Each listing shows the provider, who is eligible, the deadline and the official application link.',
     20),
    ("What does 'Verification Pending' mean on an opportunity?",
     'It means the listing is still being checked by the KPN media team. While a listing is under verification, its application link is hidden. Only apply through a listing once it is fully published with its official link.',
     21),
    ('How do I apply for an opportunity listed on KPN?',
     'KPN does not receive applications. Open the listing and follow its official application link to apply directly to the provider, and complete your application before the deadline shown.',
     22),
    ('How do I report a suspicious opportunity listing?',
     'Open the listing and use the option to report a suspicious listing, or contact the KPN media team through the Contact page. Reported listings are reviewed, and any listing found to be false or misleading is removed.',
     23),
    ('What is the Promise Tracker?',
     'The Promise Tracker records public promises made to communities in Kebbi State and follows each one with updates and evidence until it is fulfilled or its true position is known. It helps communities see what was promised and what has actually been delivered.',
     24),
    ("What does 'Verified Completed' mean on the Promise Tracker?",
     'It means KPN has checked evidence that the promise has actually been delivered. A promise is never marked verified completed based on an announcement alone.',
     25),
    ('What is the Project Tracker?',
     'The Project Tracker follows public projects across the LGAs of Kebbi State. It keeps reported information separate from verified information, and KPN only publishes project figures, such as contract details, where they are supported by documents.',
     26),
    ('How can I support KPN?',
     'You can support KPN through the Support KPN page on the website or in the app, where you will find the approved ways to donate. Support from members and well-wishers helps KPN run its community, media and youth programmes.',
     27),
    ('How do I contact KPN?',
     'You can reach KPN by email at info@kpn.com.ng, or through the Contact page on the website and in the app.',
     28),
    ('What can I do with the KPN mobile app?',
     'With the KPN app you can read Kebbi news, follow the Promise and Project Trackers, find opportunities, and report community issues. Members who sign in can also open their role dashboard, manage their profile and ID tag, and use the tools for their position.',
     29),
    ('How do I follow KPN on Telegram?',
     'KPN publishes its stories to its Telegram channel, and members can connect Telegram inside the app to receive updates and ask the KPN bot questions about the network.',
     30),
]

NEW_QUESTIONS = [
    'When was KPN founded, and is it registered?',
    'Which areas does KPN cover?',
    "What does 'One Voice, One Change' mean?",
    'How do I join KPN?',
    'What happens after I submit my membership application?',
    'How do I sign in to the KPN mobile app?',
    'Who leads KPN in my ward or LGA?',
    'What are the senatorial zones in KPN?',
    'How do I report a problem or a story from my community?',
    'What kind of issues can I report?',
    'What is the Opportunities Hub?',
    "What does 'Verification Pending' mean on an opportunity?",
    'How do I apply for an opportunity listed on KPN?',
    'How do I report a suspicious opportunity listing?',
    'What is the Promise Tracker?',
    "What does 'Verified Completed' mean on the Promise Tracker?",
    'What is the Project Tracker?',
    'How can I support KPN?',
    'How do I contact KPN?',
    'What can I do with the KPN mobile app?',
    'How do I follow KPN on Telegram?',
]


def add_faqs(apps, schema_editor):
    FAQ = apps.get_model('core', 'FAQ')
    for question, answer, order in NEW_FAQS:
        FAQ.objects.get_or_create(
            question=question,
            defaults={'answer': answer, 'order': order, 'is_active': True},
        )


def remove_faqs(apps, schema_editor):
    FAQ = apps.get_model('core', 'FAQ')
    FAQ.objects.filter(question__in=NEW_QUESTIONS).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0014_ict_admin_assignment'),
    ]

    operations = [
        migrations.RunPython(add_faqs, remove_faqs),
    ]
