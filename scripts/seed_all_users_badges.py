import sys
import datetime as dt
sys.path.insert(0, '.')
from app.db.session import SessionLocal
from app.models.user import User
from app.models.certification import Certification
from app.models.enrollment import Enrollment, EnrollmentStatus

db = SessionLocal()

users = db.query(User).all()
if not users:
    print("No users found.")
    sys.exit(1)

target_certs = [
    "PCEP - Certified Entry-Level Python Programmer",
    "Microsoft Certified: C# Developer",
    "AWS Certified Solutions Architect - Associate",
    "Oracle Certified Professional: Java SE 17 Developer",
    "Microsoft Certified: .NET Developer"
]

certs = []
for title in target_certs:
    c = db.query(Certification).filter(Certification.title == title).first()
    if c:
        certs.append(c)

added = 0
for user in users:
    for cert in certs[:3]: # give first 3 certs
        enr = db.query(Enrollment).filter(Enrollment.user_id == user.id, Enrollment.certification_id == cert.id).first()
        if not enr:
            enr = Enrollment(
                user_id=user.id,
                certification_id=cert.id,
                status=EnrollmentStatus.completed,
                progress_percent=100,
                created_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=10),
                updated_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=2)
            )
            db.add(enr)
            added += 1
        else:
            enr.status = EnrollmentStatus.completed
            enr.progress_percent = 100
            enr.updated_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=2)
            added += 1

db.commit()
print(f"Successfully seeded/updated {added} completed enrollments across all {len(users)} users.")
db.close()
