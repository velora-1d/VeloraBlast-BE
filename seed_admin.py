import database, models, auth
from database import engine, Base

def seed_admin():
    # Create tables if they don't exist
    Base.metadata.create_all(bind=engine)
    
    db = database.SessionLocal()
    try:
        admin_email = "nawawimahinutsman@gmail.com"
        admin = db.query(models.User).filter(models.User.email == admin_email).first()
        if not admin:
            hashed_pw = auth.get_password_hash("Mahin_123")
            admin_user = models.User(
                email=admin_email, 
                hashed_password=hashed_pw, 
                role="admin", 
                subscription_status="active"
            )
            db.add(admin_user)
            db.commit()
            print(f"✅ Admin user {admin_email} seeded successfully.")
        else:
            admin.role = "admin"
            admin.subscription_status = "active"
            db.commit()
            print(f"ℹ️ User {admin_email} already exists. Updated role and status.")
    except Exception as e:
        print(f"❌ Error seeding admin: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    seed_admin()
