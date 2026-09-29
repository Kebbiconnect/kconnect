"""
Management command to seed the Bot Knowledge Base with KPN official content.
Run with: python manage.py seed_bot_knowledge
"""
from django.core.management.base import BaseCommand
from telegram_integration.models import BotKnowledgeBase


KNOWLEDGE_ENTRIES = [
    {
        "topic": "KPN Website - How to Register a New Account",
        "content": (
            "To register on the KPN website, follow these steps:\n\n"
            "1. Go to https://www.kpn.com.ng and click the Login or Sign Up button at the top of the page.\n"
            "2. Look for 'Don't have an account? Register here' and click it.\n"
            "3. Fill in the registration form with your full name, email address, password, phone number, "
            "LGA of residence, and your KPN role.\n"
            "4. Click Register or Create Account to submit.\n"
            "5. Your account will be pending review by KPN administrators.\n"
            "6. Once approved, you can log in and access your dashboard.\n\n"
            "Important notes:\n"
            "- Use a valid email you have access to. KPN notifications will be sent there.\n"
            "- If you registered but cannot log in, your account may still be pending approval. "
            "Contact KPN leadership.\n"
            "- Only one account per person is allowed. Do not create duplicate accounts.\n"
            "- If you encounter errors during registration, try a different browser or clear your browser cache."
        ),
    },
    {
        "topic": "KPN Website - How to Login and Reset Password",
        "content": (
            "To log in to the KPN website:\n\n"
            "1. Go to https://www.kpn.com.ng\n"
            "2. Click the Login button at the top of the page.\n"
            "3. Enter the email address you used when you registered.\n"
            "4. Enter your password and click Login.\n"
            "5. You will be taken to your KPN Dashboard.\n\n"
            "If you forgot your password:\n"
            "1. On the login page, click Forgot Password or Reset Password.\n"
            "2. Enter your registered email address.\n"
            "3. Check your inbox for a password reset link.\n"
            "4. Click the link and create a new password.\n"
            "5. Log in with your new password.\n\n"
            "Common login problems:\n"
            "- Invalid email or password: Check carefully, ensure Caps Lock is off.\n"
            "- Account not approved: Your account is under review. Contact KPN leadership.\n"
            "- Account suspended: Contact KPN leadership to resolve this.\n"
            "- No reset email received: Check your Spam or Junk folder.\n"
            "- Still cannot log in: Contact KPN through the website or your local KPN leader."
        ),
    },
    {
        "topic": "KPN Website - Dashboard Overview and Features",
        "content": (
            "When you log in, you are taken to your personal KPN Dashboard. Here is what you will find:\n\n"
            "Your Profile:\n"
            "- View your name, role, and account status (Active, Pending, or Suspended).\n\n"
            "Telegram Connection:\n"
            "- Leadership roles require connecting your Telegram account.\n"
            "- Click the Connect Telegram button on your dashboard.\n"
            "- After authorising in Telegram, the system verifies your KPN channel membership.\n"
            "- Once verified, your dashboard is fully unlocked.\n\n"
            "Navigation Features:\n"
            "- Home: KPN website homepage.\n"
            "- Newsroom: Latest KPN news, announcements, and community reports.\n"
            "- Community: KPN community activities and updates.\n"
            "- Opportunities: Jobs, scholarships, grants, and training programmes.\n"
            "- Civic: Civic education materials.\n"
            "- Advocacy: KPN advocacy campaigns.\n"
            "- KPN Network: Patrons, Leadership Directory, Code of Conduct, and Impact page.\n"
            "- Report Story: Submit a story or report to KPN.\n\n"
            "Meetings:\n"
            "- View active and upcoming KPN meetings on your dashboard.\n"
            "- Use /present on the KPN Telegram bot to mark attendance during active meetings.\n\n"
            "Dark Mode:\n"
            "- Toggle dark or light mode using the moon or sun icon at the top right.\n\n"
            "To access the full dashboard:\n"
            "- Your account must be approved.\n"
            "- Leadership roles must connect Telegram and be verified in the official KPN channel."
        ),
    },
    {
        "topic": "KPN Telegram Bot - Commands and How to Use It",
        "content": (
            "The KPN Telegram Bot is @Kpnconnectbot. It is the official KPN Assistant on Telegram.\n\n"
            "To start:\n"
            "1. Open Telegram and search for @Kpnconnectbot.\n"
            "2. Tap the bot and type /start.\n"
            "3. The bot will introduce itself and list available commands.\n\n"
            "Available commands:\n\n"
            "/start - Starts the bot and shows a welcome message.\n\n"
            "/help - Shows all available commands.\n\n"
            "/verify - Checks if your Telegram is verified in the official KPN channel "
            "and linked to your KPN website profile.\n\n"
            "/membership - Same as /verify.\n\n"
            "/meetings - Shows currently active or upcoming scheduled KPN meetings.\n\n"
            "/present - Marks you as present at an active meeting. "
            "Your Telegram must be linked to your KPN website profile first.\n\n"
            "/kpn [your question] - Ask the KPN Assistant a question. "
            "Example: /kpn What is the KPN motto?\n\n"
            "/ask [your question] - Same as /kpn.\n\n"
            "In private chat, you can type any KPN-related question directly without a command.\n"
            "In group chats, the bot only responds to /kpn or /ask commands."
        ),
    },
    {
        "topic": "KPN Website - Connecting Telegram to Your Dashboard",
        "content": (
            "Connecting Telegram to your KPN dashboard is required for leadership roles. Steps:\n\n"
            "Step 1 - Join the official KPN Telegram channel:\n"
            "- Open Telegram and search for @officialkpn.\n"
            "- Join the channel. Wait for approval if required.\n\n"
            "Step 2 - Log in to the KPN website:\n"
            "- Go to https://www.kpn.com.ng and log in to your account.\n\n"
            "Step 3 - Go to the Connect Telegram page:\n"
            "- Click the Connect Telegram button on your dashboard.\n"
            "- Or visit https://www.kpn.com.ng/join/telegram/ directly.\n\n"
            "Step 4 - Click the Telegram Login button:\n"
            "- A blue Telegram login button will appear on the page. Click it.\n"
            "- Your Telegram app will open or a window will appear.\n\n"
            "Step 5 - Authorise the KPN bot:\n"
            "- In Telegram, click Allow or Confirm.\n"
            "- You will be redirected back to the KPN website automatically.\n\n"
            "Step 6 - Verification:\n"
            "- The system checks if you are in the official KPN Telegram channel.\n"
            "- If verified, your dashboard is fully unlocked.\n"
            "- If not verified, join @officialkpn first then try again.\n\n"
            "Common problems:\n"
            "- Page hangs after Telegram approval: Close the tab, go back to "
            "https://www.kpn.com.ng/join/telegram/ and try again.\n"
            "- Not verified: Make sure the Telegram account you authorised is the same one "
            "that is inside the @officialkpn channel.\n"
            "- Always use https://www.kpn.com.ng with the www prefix.\n"
            "- Contact your KPN LGA or State leadership if problems continue."
        ),
    },
    {
        "topic": "KPN Constitution - Full Text",
        "content": (
            "CONSTITUTION AND OPERATIONAL FRAMEWORK OF THE KEBBI PROGRESSIVE YOUTH NETWORK (KPN)\n\n"
            "PREAMBLE\n"
            "We, the members of KPN, driven by the shared vision to promote civic awareness, digital empowerment, "
            "youth advocacy, community development, charity, responsible leadership, and public participation, "
            "establish this Constitution to guide our operations from grassroots to State level.\n\n"
            "ARTICLE I - NAME: Kebbi Progressive Youth Network (KPN)\n\n"
            "ARTICLE II - MOTTO: One Voice, One Change.\n\n"
            "ARTICLE III - VISION: To build a digitally empowered generation of young people leading positive "
            "change for a better, united, and progressive Kebbi State.\n\n"
            "ARTICLE IV - MISSION: To build a strong, connected social media and community network across "
            "Kebbi State, creating a platform where information, ideas, opportunities, and citizen voices "
            "can be shared and heard.\n\n"
            "ARTICLE V - AIMS:\n"
            "1. Amplify voices of young people through social media and digital tools.\n"
            "2. Support peace, unity, and community development.\n"
            "3. Build a strong digital and community network from Ward to State level.\n"
            "4. Promote civic education and public awareness.\n"
            "5. Empower youth for leadership, advocacy, and digital skills.\n"
            "6. Attract donors, partners, and development organisations.\n"
            "7. Organise charity programmes and humanitarian activities.\n"
            "8. Promote digital literacy and online safety.\n"
            "9. Create educational, professional, and economic opportunities.\n"
            "10. Build a trusted community information and reporting network.\n"
            "11. Promote responsible journalism and accurate public information.\n\n"
            "ARTICLE VI - MEMBERSHIP:\n"
            "Eligibility: Open to youths who support KPN vision, are willing to participate, respect the "
            "Constitution, are residents or indigenes of Kebbi State, and provide accurate information.\n\n"
            "Duties of Members:\n"
            "1. Support official KPN programmes and verified information.\n"
            "2. Participate in campaigns, training, and community activities.\n"
            "3. Promote peace, unity, and responsible citizenship.\n"
            "4. Respect the Constitution, leadership, and organisational decisions.\n"
            "5. Avoid spreading false or harmful information through KPN platforms.\n"
            "6. Report genuine community issues through approved KPN channels.\n"
            "7. Protect the reputation and credibility of KPN.\n\n"
            "Loss of Membership: Due to persistent inactivity, hate speech, fraud, spreading false information, "
            "misuse of KPN platforms, or other serious misconduct.\n\n"
            "ARTICLE VII - STRUCTURE: Ward Community Teams, LGA Network Teams, "
            "Senatorial Leadership Teams, State Executive Team.\n\n"
            "ARTICLE VIII - STATE EXECUTIVE TEAM (20 positions):\n"
            "1. President\n2. Vice President\n3. General Secretary\n4. Assistant General Secretary\n"
            "5. Director of Monitoring and Compliance\n6. Director of Legal Affairs and Ethics\n"
            "7. Director of Finance\n8. Finance Operations Officer\n"
            "9. Director of Community Engagement\n10. Assistant Director of Community Engagement\n"
            "11. Director of Programmes and Events\n12. Assistant Director of Programmes and Events\n"
            "13. Director of Audit and Accountability\n14. Director of Member Support and Welfare\n"
            "15. Director of Youth Development\n16. Director of Women's Development\n"
            "17. Assistant Director of Women's Development\n18. Director of Media and Communications\n"
            "19. Assistant Director of Media and Communications\n"
            "20. Director of Public Relations and Partnerships\n\n"
            "SENATORIAL ZONES (3 zones, 3 roles each):\n"
            "Zones: Kebbi North, Kebbi Central, Kebbi South.\n"
            "Roles: Senatorial Director, Senatorial Administrative Officer, Senatorial Communications Officer.\n\n"
            "LGA NETWORK TEAMS (10 roles per LGA):\n"
            "LGA Network Lead, LGA Administrative Officer, LGA Programmes Officer, LGA Finance Officer, "
            "LGA Communications Officer, LGA Monitoring Officer, LGA Women's Development Officer, "
            "LGA Member Support Officer, LGA Community Engagement Officer, LGA Adviser.\n\n"
            "WARD COMMUNITY TEAMS (8 roles per ward):\n"
            "Ward Community Lead, Ward Administrative Officer, Ward Programmes Officer, Ward Finance Officer, "
            "Ward Communications Officer, Ward Monitoring Officer, Ward Community Support Officer, Ward Adviser.\n\n"
            "ARTICLE IX - TENURE: 4-year term, renewable once. Elections must be fair, peaceful, and transparent.\n\n"
            "ARTICLE X - FUNDING: Through donations, contributions, fundraising, NGO support, and grants. "
            "Managed by Director of Finance. Quarterly reports presented to State Executive Team.\n\n"
            "ARTICLE XI - MEETINGS: Virtual meetings via WhatsApp and Telegram. "
            "Annual General Assembly reviews activities and finances.\n\n"
            "ARTICLE XII - CODE OF CONDUCT: No hate speech, tribalism, discrimination, harassment, or violence. "
            "All communication must be factual, responsible, and respectful. "
            "Violations lead to warning, suspension, or expulsion.\n\n"
            "ARTICLE XIV - KPN INFORMATION CLASSIFICATIONS:\n"
            "- KPN VERIFIED: Checked and supported by reliable evidence.\n"
            "- KPN CONFIRMED: Confirmed by multiple reliable sources.\n"
            "- KPN DEVELOPING: Still being checked, may receive updates.\n"
            "- KPN COMMUNITY ALERT: Urgent matter affecting public welfare or safety.\n"
            "- KPN OPPORTUNITY: Legitimate jobs, scholarships, grants, or training programmes.\n\n"
            "ARTICLE XV - AMENDMENT: By two-thirds majority of active members during a General Assembly.\n\n"
            "ARTICLE XVI - ADOPTION: Adopted in 2025 by the Founding Members of KPN, Kebbi State, Nigeria."
        ),
    },
    {
        "topic": "KPN Leadership - How to Find Who Holds a Specific Position",
        "content": (
            "For questions about who holds a specific leadership position such as the Ward Adviser of "
            "a particular ward, or the LGA Network Lead of a particular LGA, visit the KPN Leadership "
            "Directory on the website:\n\n"
            "https://www.kpn.com.ng/leadership/\n\n"
            "This page shows the full, up-to-date list of KPN leaders at all levels including "
            "State Executive, Senatorial, LGA, and Ward.\n\n"
            "If the information is not on the website, contact your LGA Network Lead or the "
            "KPN State Executive Team directly.\n\n"
            "For privacy reasons, the bot cannot display personal phone numbers or private contact "
            "details of individual leaders.\n\n"
            "KPN Leadership Levels Summary:\n"
            "- State Executive Team: 20 positions headed by the President.\n"
            "- Senatorial Teams: 3 zones (Kebbi North, Kebbi Central, Kebbi South), 3 roles each.\n"
            "- LGA Network Teams: 10 roles per LGA across all 21 LGAs of Kebbi State.\n"
            "- Ward Community Teams: 8 roles per ward across all wards of Kebbi State.\n\n"
            "Each ward has a Ward Adviser as one of its 8 roles. "
            "Each LGA has an LGA Adviser as one of its 10 roles. "
            "To find who holds a specific role in a specific ward or LGA, "
            "please visit the Leadership Directory on the KPN website."
        ),
    },
]


class Command(BaseCommand):
    help = "Seed the Bot Knowledge Base with official KPN content"

    def handle(self, *args, **options):
        created = updated = 0
        for entry in KNOWLEDGE_ENTRIES:
            obj, was_created = BotKnowledgeBase.objects.get_or_create(
                topic=entry["topic"],
                defaults={"content": entry["content"], "is_active": True},
            )
            if was_created:
                created += 1
                self.stdout.write(self.style.SUCCESS(f"  CREATED: {entry['topic']}"))
            else:
                obj.content = entry["content"]
                obj.is_active = True
                obj.save()
                updated += 1
                self.stdout.write(self.style.WARNING(f"  UPDATED: {entry['topic']}"))

        total = BotKnowledgeBase.objects.filter(is_active=True).count()
        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone! {created} created, {updated} updated. "
                f"Total active brain entries: {total}"
            )
        )
