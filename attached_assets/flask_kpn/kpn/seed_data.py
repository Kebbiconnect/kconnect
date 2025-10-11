from flask import current_app
from models import *
from werkzeug.security import generate_password_hash
from datetime import datetime

def seed_database():
    from extensions import db
    import os
    
    print("Seeding database with Kebbi State data...")
    
    # Handle database schema migrations for new fields
    try:
        # Check if new disciplinary action columns exist and add them if missing
        inspector = db.inspect(db.engine)
        disciplinary_columns = [col['name'] for col in inspector.get_columns('disciplinary_actions')]
        
        missing_columns = []
        new_columns = [
            ('approval_status', "VARCHAR(20) DEFAULT 'not_required'"),
            ('approval_required', "BOOLEAN DEFAULT FALSE"),
            ('approved_by_id', "INTEGER"),
            ('approved_at', "TIMESTAMP"),
            ('approval_notes', "TEXT")
        ]
        
        for col_name, col_def in new_columns:
            if col_name not in disciplinary_columns:
                missing_columns.append((col_name, col_def))
        
        if missing_columns:
            print(f"Adding missing disciplinary action columns: {[col[0] for col in missing_columns]}")
            for col_name, col_def in missing_columns:
                try:
                    db.session.execute(db.text(f"ALTER TABLE disciplinary_actions ADD COLUMN {col_name} {col_def}"))
                    db.session.commit()
                    print(f"Successfully added column: {col_name}")
                except Exception as e:
                    print(f"Note: Column {col_name} may already exist: {e}")
                    db.session.rollback()  # Rollback failed transaction
            
            # Add foreign key constraints separately (SQLite limitation)
            try:
                # SQLite doesn't support adding foreign keys to existing tables easily
                # We'll handle this constraint in the application layer
                pass
            except Exception as e:
                print(f"Note: Foreign key constraint handling: {e}")
        
        # Check if new events columns exist and add them if missing (for online meeting support)
        try:
            events_columns = [col['name'] for col in inspector.get_columns('events')]
            
            missing_event_columns = []
            new_event_columns = [
                ('meeting_type', "VARCHAR(20) DEFAULT 'in_person'"),
                ('meeting_url', "VARCHAR(500)"),
                ('meeting_id', "VARCHAR(100)"),
                ('meeting_password', "VARCHAR(100)")
            ]
            
            for col_name, col_def in new_event_columns:
                if col_name not in events_columns:
                    missing_event_columns.append((col_name, col_def))
            
            if missing_event_columns:
                print(f"Adding missing events columns for online meeting support: {[col[0] for col in missing_event_columns]}")
                for col_name, col_def in missing_event_columns:
                    try:
                        db.session.execute(db.text(f"ALTER TABLE events ADD COLUMN {col_name} {col_def}"))
                        db.session.commit()
                        print(f"Successfully added column: {col_name}")
                    except Exception as e:
                        print(f"Note: Column {col_name} may already exist: {e}")
                        db.session.rollback()  # Rollback failed transaction
            else:
                print("Events table already has all required columns for online meeting support")
                        
        except Exception as e:
            print(f"Events table migration check completed with note: {e}")
        
    except Exception as e:
        print(f"Schema migration check completed with note: {e}")
    
    # Check if geographical data already exists
    zones_exist = Zone.query.count() > 0
    if zones_exist:
        print("Geographical data already exists, skipping zone/LGA/ward creation...")
    
    # Handle ICT_ADMIN migration - convert to ADMIN role (remove ICT_ADMIN entirely)
    try:
        # Use text casting to handle Postgres enum issues safely
        result = db.session.execute(db.text("UPDATE users SET role_type = 'admin' WHERE CAST(role_type AS TEXT) = 'ict_admin'"))
        rows_updated = result.rowcount if hasattr(result, 'rowcount') else 0
        db.session.commit()
        if rows_updated > 0:
            print(f"Migrated {rows_updated} ICT_ADMIN users to ADMIN role")
        else:
            print("No ICT_ADMIN users found to migrate")
    except Exception as e:
        print(f"ICT_ADMIN migration note: {e}")
        db.session.rollback()
    
    # Check if essential users already exist
    admin_exists = User.query.filter_by(username='Kpn20').first() is not None
    state_coord_exists = User.query.filter_by(username='Nasirukgw').first() is not None
    
    # Create geographical data only if it doesn't exist
    if not zones_exist:
        # Create Zones
        zones_data = [
            {'name': 'Kebbi North', 'slug': 'kebbi-north'},
            {'name': 'Kebbi Central', 'slug': 'kebbi-central'},
            {'name': 'Kebbi South', 'slug': 'kebbi-south'}
        ]
        
        zones = {}
        for zone_data in zones_data:
            zone = Zone(name=zone_data['name'], slug=zone_data['slug'])
            db.session.add(zone)
            db.session.flush()
            zones[zone_data['name']] = zone
        
        # Create LGAs with their zones
        lgas_data = {
            'Kebbi North': ['Arewa', 'Argungu', 'Augie', 'Bagudo', 'Dandi', 'Suru'],
            'Kebbi Central': ['Aliero', 'Birnin Kebbi', 'Bunza', 'Gwandu', 'Jega', 'Kalgo', 'Koko/Besse', 'Maiyama'],
            'Kebbi South': ['Danko/Wasagu', 'Fakai', 'Ngaski', 'Sakaba', 'Shanga', 'Yauri', 'Zuru']
        }
        
        lgas = {}
        for zone_name, lga_list in lgas_data.items():
            zone = zones[zone_name]
            for lga_name in lga_list:
                lga = LGA(name=lga_name, slug=lga_name.lower().replace('/', '-'), zone_id=zone.id)
                db.session.add(lga)
                db.session.flush()
                lgas[lga_name] = lga
        
        # Create Wards for each LGA
        wards_data = {
            'Aliero': ['Aliero Dangaladima I', 'Aliero Dangaladima II', 'Aliero S/Fada I', 'Aliero S/Fada II', 'Danwarai', 'Jiga Birni', 'Jiga Makera', 'Kashin Zama', 'Rafin Bauna', 'Sabiyal'],
            'Arewa': ['Bui', 'Chibike', 'Daura', 'Gorun Dikko', 'Falde', 'Feske/Jaffeji', 'Gumumdai/Rafin Tsaka', 'Kangiwa', 'Laima/Jantullu', 'Sarka/Dantsoho', 'Yeldu'],
            'Argungu': ['Gotomo', 'Dikko', 'Felande', 'Galadima', 'Gulma', 'Gwazange', 'Kokani North', 'Kokani South', 'Lailaba', 'Sauwa/Kaurar Sani', 'Tungar Zazzagawa'],
            'Augie': ['Augie North', 'Augie South', 'Bagaye/Mera', 'Bayawa North', 'Bayawa South', 'Birnin Tudu/Gudale', 'Bubuce', 'Dundaye', 'Tiggi', 'Yola'],
            'Bagudo': ['Bagudo', 'Bahindi/Boki-Doma', 'Bani/Tsamiya/Kali', 'Illo/Sabon Gari/Yantau', 'Kaoje/Gwamba', 'Kende/Kurgu', 'Lafagu/Gante', 'Lolo/Giris', 'Matsinka/Geza', 'Sharabi/Kwanguwai', 'Zagga/Kwasara'],
            'Birnin Kebbi': ['Nassarawa I', 'Nassarawa II', 'Marafa', 'Dangaladima', 'Kola/Tarasa', 'Makera', 'Maurida', 'Gwadangaji', 'Zauro', 'Gawasu', 'Kardi/Yamama', 'Lagga', 'Gulumbe', 'Ambursa', 'Ujariyo'],
            'Bunza': ['Bunza Marafa', 'Bunza Dangaladima', 'Gwade', 'Maidahini', 'Raha', 'Sabon Birni', 'Salwai', 'Tilli/Hilema', 'Tunga', 'Zogrima'],
            'Dandi': ['Bani Zumbu', 'Buma', 'Dolekaina', 'Fana', 'Maihausawa', 'Kyangakwai', 'Geza', 'Kamba', 'Kwakkwaba', 'Maigwaza', 'Shiko'],
            'Fakai': ['Bajida', 'Bangu/Garinisa', 'Birnin Tudu', 'Mahuta', 'Gulbin Kuka/Maijarhula', 'Maikende', 'Kangi', 'Fakai/Zussun', 'Marafa', 'Penin Amana/Penin Gaba'],
            'Gwandu': ['Cheberu/Bada', 'Dalijan', 'Dodoru', 'Gulmare', 'Gwandu Marafa', 'Gwandu Sarkin Fawa', 'Kambaza', 'Maruda', 'Malisa', 'Masama Kwasgara'],
            'Jega': ['Alelu/Gehuru', 'Dangamaji', 'Dunbegu/Bausara', 'Gindi/Nassarawa/Kyarmi/Galbi', 'Jandutsi/Birnin Malam', 'Jega Firchin', 'Jega Kokani', 'Jega Magaji B', 'Jega Magaji A', 'Katanga/Fagada', 'Kimba'],
            'Kalgo': ['Badariya/Magarza', 'Dangoma/Gayi', 'Diggi', 'Etene', 'Kalgo', 'Kuka', 'Mutubari', 'Nayilwa', 'Wurogauri', 'Zuguru'],
            'Koko/Besse': ['Koko Magaji', 'Illela/Sabon Gari', 'Koko Firchin', 'Dada/Alelu', 'Jadadi', 'Lani/Manyan/Tafukka/Shiba', 'Besse', 'Takware', 'Dutsin Mari/Dulmeru', 'Zariya Kalakala/Amiru', 'Madacci/Firini', 'Maikwara/Karamar Damra/Bakoshi'],
            'Maiyama': ['Andarai/Kurunkudu/Zugun Liba', 'Giwa Tazo/Zara', 'Gumbin Kure', 'Karaye/Dogondaji', 'Kawara/S/Sara/Yarkamba', 'Kuberu/Gidiga', 'Liba/Danwa/Kuka Kogo', 'Maiyama', 'Mungadi/Botoro', 'Sambawa/Mayalo', 'Sarandosa/Gubba'],
            'Ngaski': ['Birnin Yauri', 'Gafara Machupa', 'Garin Baka/Makarin', 'Kwakwaran', 'Libata/Kwangia', 'Kambuwa/Danmaraya', 'Makawa Uleira', 'Ngaski', 'Utono/Hoge', 'Wara'],
            'Sakaba': ['Adai', 'Dankolo', 'Doka/Bere', 'Gelwasa', 'Janbirni', 'Maza/Maza', 'Makuku', 'Sakaba', 'Tudun Kuka', 'Fada'],
            'Shanga': ['Atuwo', 'Binuwa/Gebbe/Bukunji', 'Dugu Tsoho/Dugu Raha', 'Kawara/Ingu/Sargo', 'Rafin Kirya/Tafki Tara', 'Sakace/Golongo/Hundeji', 'Sawashi', 'Shanga', 'Takware', 'Yarbesse'],
            'Suru': ['Aljannare', 'Bandan', 'Barbarejo', 'Bakuwa', 'Dakingari', 'Dandane', 'Daniya/Shema', 'Ginga', 'Giro', 'Kwaifa', 'Suru'],
            'Danko/Wasagu': ['Ayu', 'Bena', 'Dan Umaru/Mairairai', 'Danko/Maga', 'Kanya', 'Kyabu/Kandu', 'Ribah/Machika', 'Waje', 'Wasagu', 'Yalmo/Shindi', 'Gwanfi/Kele'],
            'Yauri': ['Chulu/Koma', 'Gungun Sarki', 'Jijima', 'Tondi', 'Yelwa Central', 'Yelwa East', 'Yelwa North', 'Yelwa South', 'Yelwa West', 'Zamare'],
            'Zuru': ['Bedi', 'Ciroman Dabai', 'Isgogo/Dago', 'Manga/Ushe', 'Rafin Zuru', 'Rikoto', 'Rumu/Daben/Seme', 'Senchi', 'Taduga', 'Zodi']
        }
        
        for lga_name, ward_list in wards_data.items():
            lga = lgas.get(lga_name)
            if lga:
                for ward_name in ward_list:
                    # Create unique slug by combining LGA and ward name
                    unique_slug = f"{lga_name.lower().replace('/', '-').replace(' ', '-')}-{ward_name.lower().replace('/', '-').replace(' ', '-')}"
                    ward = Ward(name=ward_name, slug=unique_slug, lga_id=lga.id)
                    db.session.add(ward)
    
    # Create essential user accounts only if they don't exist
    # Use specific credentials as requested
    admin_password = 'Kpn@12?'
    state_coord_password = 'Maitonka@123'
    
    if not admin_exists:
        # Create default admin account
        admin_user = User(
            username='Kpn20',
            email='kpn2020@gmail.com',
            full_name='KPN Admin',
            whatsapp_number='+2348102444491',  # Required field
            role_type=RoleType.ADMIN,
            approval_status=ApprovalStatus.APPROVED,
            facebook_verified=True  # Require proper verification
        )
        admin_user.set_password(admin_password)
        db.session.add(admin_user)
        print("Created KPN Admin account with temporary password - please change on first login")
    
    
    if not state_coord_exists:
        # Create State Coordinator account (only essential executive)
        state_coord_user = User(
            username='Nasirukgw',
            email='nasirusaidukgw@gmail.com',
            full_name='Nasiru Saidu',
            whatsapp_number='+2348037851112',  # Required field
            role_type=RoleType.EXECUTIVE,
            role_title='State Coordinator',
            approval_status=ApprovalStatus.APPROVED,
            facebook_verified=True  # Require proper verification
        )
        state_coord_user.set_password(state_coord_password)
        db.session.add(state_coord_user)
        print("Created State Coordinator account with temporary password - please change on first login")
    
    # Remove any test users that shouldn't exist
    test_usernames = ['Danyola', 'AuntyAmina']
    for username in test_usernames:
        test_user = User.query.filter_by(username=username).first()
        if test_user:
            db.session.delete(test_user)
    
    # Create sample donation accounts only if they don't exist
    if Donation.query.count() == 0:
        donations_data = [
            {
                'bank_name': 'First Bank of Nigeria',
                'account_name': 'Kebbi Progressive Network',
                'account_number': '3085123456',
                'description': 'Main donation account for KPN activities'
            },
            {
                'bank_name': 'Zenith Bank',
                'account_name': 'KPN Welfare Fund',
                'account_number': '1014567890',
                'description': 'Special account for welfare and charity activities'
            }
        ]
        
        for donation_data in donations_data:
            donation = Donation(**donation_data)
            db.session.add(donation)
    
    db.session.commit()
    print("Database seeded successfully with Kebbi State data!")