from django.core.management.base import BaseCommand
from leadership.models import Zone, LGA, Ward, RoleDefinition

class Command(BaseCommand):
    help = 'Seeds the database with Kebbi State location data and role definitions'

    def handle(self, *args, **options):
        self.stdout.write('Seeding Zones, LGAs, and Wards...')
        
        kebbi_north = Zone.objects.get_or_create(name='Kebbi North')[0]
        kebbi_central = Zone.objects.get_or_create(name='Kebbi Central')[0]
        kebbi_south = Zone.objects.get_or_create(name='Kebbi South')[0]
        
        lga_data = {
            'Kebbi North': {
                'Arewa': ['Bui', 'Chibike', 'Daura', 'Gorun Dikko', 'Falde', 'Feske/Jaffeji', 'Gumumdai/Rafin Tsaka', 'Kangiwa', 'Laima/Jantullu', 'Sarka/Dantsoho', 'Yeldu'],
                'Argungu': ['Gotomo', 'Dikko', 'Felande', 'Galadima', 'Gulma', 'Gwazange', 'Kokani North', 'Kokani South', 'Lailaba', 'Sauwa/Kaurar Sani', 'Tungar Zazzagawa'],
                'Augie': ['Augie North', 'Augie South', 'Bagaye/Mera', 'Bayawa North', 'Bayawa South', 'Birnin Tudu/Gudale', 'Bubuce', 'Dundaye', 'Tiggi', 'Yola'],
                'Bagudo': ['Bagudo', 'Bahindi/Boki-Doma', 'Bani/Tsamiya/Kali', 'Illo/Sabon Gari/Yantau', 'Kaoje/Gwamba', 'Kende/Kurgu', 'Lafagu/Gante', 'Lolo/Giris', 'Matsinka/Geza', 'Sharabi/Kwanguwai', 'Zagga/Kwasara'],
                'Dandi': ['Bani Zumbu', 'Buma', 'Dolekaina', 'Fana', 'Maihausawa', 'Kyangakwai', 'Geza', 'Kamba', 'Kwakkwaba', 'Maigwaza', 'Shiko'],
                'Suru': ['Aljannare', 'Bandan', 'Barbarejo', 'Bakuwa', 'Dakingari', 'Dandane', 'Daniya/Shema', 'Ginga', 'Giro', 'Kwaifa', 'Suru'],
            },
            'Kebbi Central': {
                'Aliero': ['Aliero Dangaladima I', 'Aliero Dangaladima II', 'Aliero S/Fada I', 'Aliero S/Fada II', 'Danwarai', 'Jiga Birni', 'Jiga Makera', 'Kashin Zama', 'Rafin Bauna', 'Sabiyal'],
                'Birnin Kebbi': ['Nassarawa I', 'Nassarawa II', 'Marafa', 'Dangaladima', 'Kola/Tarasa', 'Makera', 'Maurida', 'Gwadangaji', 'Zauro', 'Gawasu', 'Kardi/Yamama', 'Lagga', 'Gulumbe', 'Ambursa', 'Ujariyo'],
                'Bunza': ['Bunza Marafa', 'Bunza Dangaladima', 'Gwade', 'Maidahini', 'Raha', 'Sabon Birni', 'Salwai', 'Tilli/Hilema', 'Tunga', 'Zogrima'],
                'Gwandu': ['Cheberu/Bada', 'Dalijan', 'Dodoru', 'Gulmare', 'Gwandu Marafa', 'Gwandu Sarkin Fawa', 'Kambaza', 'Maruda', 'Malisa', 'Masama Kwasgara'],
                'Jega': ['Alelu/Gehuru', 'Dangamaji', 'Dunbegu/Bausara', 'Gindi/Nassarawa/Kyarmi/Galbi', 'Jandutsi/Birnin Malam', 'Jega Firchin', 'Jega Kokani', 'Jega Magaji B', 'Jega Magaji A', 'Katanga/Fagada', 'Kimba'],
                'Kalgo': ['Badariya/Magarza', 'Dangoma/Gayi', 'Diggi', 'Etene', 'Kalgo', 'Kuka', 'Mutubari', 'Nayilwa', 'Wurogauri', 'Zuguru'],
                'Koko/Besse': ['Koko Magaji', 'Illela/Sabon Gari', 'Koko Firchin', 'Dada/Alelu', 'Jadadi', 'Lani/Manyan/Tafukka/Shiba', 'Besse', 'Takware', 'Dutsin Mari/Dulmeru', 'Zariya Kalakala/Amiru', 'Madacci/Firini', 'Maikwara/Karamar Damra/Bakoshi'],
                'Maiyama': ['Andarai/Kurunkudu/Zugun Liba', 'Giwa Tazo/Zara', 'Gumbin Kure', 'Karaye/Dogondaji', 'Kawara/S/Sara/Yarkamba', 'Kuberu/Gidiga', 'Liba/Danwa/Kuka Kogo', 'Maiyama', 'Mungadi/Botoro', 'Sambawa/Mayalo', 'Sarandosa/Gubba'],
            },
            'Kebbi South': {
                'Wasagu/Danko': ['Ayu', 'Bena', 'Dan Umaru/Mairairai', 'Danko/Maga', 'Kanya', 'Kyabu/Kandu', 'Ribah/Machika', 'Waje', 'Wasagu', 'Yalmo/Shindi', 'Gwanfi/Kele'],
                'Fakai': ['Bajida', 'Bangu/Garinisa', 'Birnin Tudu', 'Mahuta', 'Gulbin Kuka/Maijarhula', 'Maikende', 'Kangi', 'Fakai/Zussun', 'Marafa', 'Penin Amana/Penin Gaba'],
                'Ngaski': ['Birnin Yauri', 'Gafara Machupa', 'Garin Baka/Makarin', 'Kwakwaran', 'Libata/Kwangia', 'Kambuwa/Danmaraya', 'Makawa Uleira', 'Ngaski', 'Utono/Hoge', 'Wara'],
                'Sakaba': ['Adai', 'Dankolo', 'Doka/Bere', 'Gelwasa', 'Janbirni', 'Maza/Maza', 'Makuku', 'Sakaba', 'Tudun Kuka', 'Fada'],
                'Shanga': ['Atuwo', 'Binuwa/Gebbe/Bukunji', 'Dugu Tsoho/Dugu Raha', 'Kawara/Ingu/Sargo', 'Rafin Kirya/Tafki Tara', 'Sakace/Golongo/Hundeji', 'Sawashi', 'Shanga', 'Takware', 'Yarbesse'],
                'Yauri': ['Chulu/Koma', 'Gungun Sarki', 'Jijima', 'Tondi', 'Yelwa Central', 'Yelwa East', 'Yelwa North', 'Yelwa South', 'Yelwa West', 'Zamare'],
                'Zuru': ['Bedi', 'Ciroman Dabai', 'Isgogo/Dago', 'Manga/Ushe', 'Rafin Zuru', 'Rikoto', 'Rumu/Daben/Seme', 'Senchi', 'Taduga', 'Zodi'],
            }
        }
        
        for zone_name, lgas in lga_data.items():
            zone = Zone.objects.get(name=zone_name)
            for lga_name, wards in lgas.items():
                lga, created = LGA.objects.get_or_create(name=lga_name, zone=zone)
                for ward_name in wards:
                    Ward.objects.get_or_create(name=ward_name, lga=lga)
        
        self.stdout.write(self.style.SUCCESS('Successfully seeded location data!'))
        
        self.stdout.write('Seeding Role Definitions...')
        
        state_roles = [
            (1, 'President'),
            (2, 'Vice President'),
            (3, 'General Secretary'),
            (4, 'Assistant General Secretary'),
            (5, 'State Supervisor'),
            (6, 'Legal & Ethics Adviser'),
            (7, 'Treasurer'),
            (8, 'Financial Secretary'),
            (9, 'Director of Mobilization'),
            (10, 'Assistant Director of Mobilization'),
            (11, 'Organizing Secretary'),
            (12, 'Assistant Organizing Secretary'),
            (13, 'Auditor General'),
            (14, 'Welfare Officer'),
            (15, 'Youth Development & Empowerment Officer'),
            (16, 'Women Leader'),
            (17, 'Assistant Women Leader'),
            (18, 'Director of Media & Publicity'),
            (19, 'Assistant Director of Media & Publicity'),
            (20, 'Public Relations & Community Engagement Officer'),
        ]
        
        zonal_roles = [
            (1, 'Zonal Coordinator'),
            (2, 'Zonal Secretary'),
            (3, 'Zonal Publicity Officer'),
        ]
        
        lga_roles = [
            (1, 'LGA Coordinator'),
            (2, 'Secretary'),
            (3, 'Organizing Secretary'),
            (4, 'Treasurer'),
            (5, 'Publicity Officer'),
            (6, 'LGA Supervisor'),
            (7, 'Women Leader'),
            (8, 'Welfare Officer'),
            (9, 'Director of Contact and Mobilization'),
            (10, 'LGA Adviser'),
        ]
        
        ward_roles = [
            (1, 'Ward Coordinator'),
            (2, 'Secretary'),
            (3, 'Organizing Secretary'),
            (4, 'Treasurer'),
            (5, 'Publicity Officer'),
            (6, 'Financial Secretary'),
            (7, 'Ward Supervisor'),
            (8, 'Ward Adviser'),
        ]
        
        for seat_number, title in state_roles:
            RoleDefinition.objects.get_or_create(
                tier='STATE',
                title=title,
                defaults={'seat_number': seat_number}
            )
        
        for seat_number, title in zonal_roles:
            RoleDefinition.objects.get_or_create(
                tier='ZONAL',
                title=title,
                defaults={'seat_number': seat_number}
            )
        
        for seat_number, title in lga_roles:
            RoleDefinition.objects.get_or_create(
                tier='LGA',
                title=title,
                defaults={'seat_number': seat_number}
            )
        
        for seat_number, title in ward_roles:
            RoleDefinition.objects.get_or_create(
                tier='WARD',
                title=title,
                defaults={'seat_number': seat_number}
            )
        
        self.stdout.write(self.style.SUCCESS('Successfully seeded role definitions!'))
        
        total_zones = Zone.objects.count()
        total_lgas = LGA.objects.count()
        total_wards = Ward.objects.count()
        total_roles = RoleDefinition.objects.count()
        
        self.stdout.write(self.style.SUCCESS(f'\n=== Seed Summary ==='))
        self.stdout.write(self.style.SUCCESS(f'Zones: {total_zones}'))
        self.stdout.write(self.style.SUCCESS(f'LGAs: {total_lgas}'))
        self.stdout.write(self.style.SUCCESS(f'Wards: {total_wards}'))
        self.stdout.write(self.style.SUCCESS(f'Role Definitions: {total_roles}'))
        self.stdout.write(self.style.SUCCESS('===================\n'))
