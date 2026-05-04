import sys
sys.path.insert(0, '.')
from app.db.session import engine, SessionLocal
from app.models.certification import Certification
from sqlalchemy import text

db = SessionLocal()

try:
    # Safely add the column if it doesn't exist
    db.execute(text("ALTER TABLE certifications ADD COLUMN badge_image_url VARCHAR(500);"))
    db.commit()
    print("Added badge_image_url column.")
except Exception as e:
    db.rollback()
    print("Column might already exist. Proceeding...")

certs_to_add = [
    {
        "title": "Oracle Certified Professional: Java SE 17 Developer",
        "provider": "Oracle",
        "level": "Professional",
        "category": "Software Development",
        "badge_image_url": "https://img.shields.io/badge/Java-Oracle_Certified-ED8B00?style=for-the-badge&logo=oracle&logoColor=white",
        "exam_cost": 245,
        "estimated_hours": 120,
        "description": "Demonstrate your proficiency in Java SE 17 and your deep understanding of Java technologies.",
        "course_url": "https://www.udemy.com/course/java-se-17-developer-1z0-829-certification/",
        "official_exam_url": "https://education.oracle.com/oracle-certified-professional-java-se-17-developer/trackp_829"
    },
    {
        "title": "PCEP - Certified Entry-Level Python Programmer",
        "provider": "Python Institute",
        "level": "Beginner",
        "category": "Software Development",
        "badge_image_url": "https://img.shields.io/badge/Python-Certified-3776AB?style=for-the-badge&logo=python&logoColor=white",
        "exam_cost": 59,
        "estimated_hours": 40,
        "description": "A professional credential that measures your ability to accomplish coding tasks related to the essentials of programming in the Python language.",
        "course_url": "https://www.udemy.com/course/pcep-certified-entry-level-python-programmer-certification/",
        "official_exam_url": "https://pythoninstitute.org/pcep"
    },
    {
        "title": "CLA - C Programming Language Certified Associate",
        "provider": "C++ Institute",
        "level": "Associate",
        "category": "Software Development",
        "badge_image_url": "https://img.shields.io/badge/C-Certified-A8B9CC?style=for-the-badge&logo=c&logoColor=white",
        "exam_cost": 295,
        "estimated_hours": 60,
        "description": "Measures your ability to accomplish coding tasks related to the basics of programming in the C language.",
        "course_url": "https://www.udemy.com/course/c-programming-for-beginners-/",
        "official_exam_url": "https://cppinstitute.org/cla-c-programming-language-certified-associate"
    },
    {
        "title": "Microsoft Certified: C# Developer",
        "provider": "Microsoft",
        "level": "Associate",
        "category": "Software Development",
        "badge_image_url": "https://img.shields.io/badge/C%23-Microsoft_Certified-239120?style=for-the-badge&logo=c-sharp&logoColor=white",
        "exam_cost": 165,
        "estimated_hours": 80,
        "description": "Demonstrate your skills in writing foundational C# code.",
        "course_url": "https://www.udemy.com/course/csharp-tutorial-for-beginners/",
        "official_exam_url": "https://learn.microsoft.com/en-us/credentials/certifications/c-sharp-developer/"
    },
    {
        "title": "Microsoft Certified: .NET Developer",
        "provider": "Microsoft",
        "level": "Professional",
        "category": "Software Development",
        "badge_image_url": "https://img.shields.io/badge/.NET-Microsoft_Certified-512BD4?style=for-the-badge&logo=dotnet&logoColor=white",
        "exam_cost": 165,
        "estimated_hours": 100,
        "description": "Build high-performance, modern applications using .NET.",
        "course_url": "https://www.udemy.com/course/complete-dotnet-core-mvc/",
        "official_exam_url": "https://learn.microsoft.com/en-us/credentials/certifications/dotnet-developer/"
    },
    {
        "title": "AWS Certified Solutions Architect - Associate",
        "provider": "Amazon Web Services",
        "level": "Associate",
        "category": "Cloud Computing",
        "badge_image_url": "https://img.shields.io/badge/AWS-Solutions_Architect-232F3E?style=for-the-badge&logo=amazon-aws&logoColor=white",
        "exam_cost": 150,
        "estimated_hours": 130,
        "description": "Showcase your knowledge and skills in AWS technology, across a wide range of AWS services.",
        "course_url": "https://www.udemy.com/course/aws-certified-solutions-architect-associate-saa-c03/",
        "official_exam_url": "https://aws.amazon.com/certification/certified-solutions-architect-associate/"
    },
    {
        "title": "Microsoft Certified: Azure Developer Associate",
        "provider": "Microsoft",
        "level": "Associate",
        "category": "Cloud Computing",
        "badge_image_url": "https://img.shields.io/badge/Azure-Developer_Associate-0089D6?style=for-the-badge&logo=microsoft-azure&logoColor=white",
        "exam_cost": 165,
        "estimated_hours": 120,
        "description": "Subject matter expertise in designing, building, testing, and maintaining cloud applications and services on Microsoft Azure.",
        "course_url": "https://www.udemy.com/course/70532-developing-microsoft-azure-solutions/",
        "official_exam_url": "https://learn.microsoft.com/en-us/credentials/certifications/azure-developer/"
    },
    {
        "title": "Salesforce Certified Administrator",
        "provider": "Salesforce",
        "level": "Beginner",
        "category": "CRM",
        "badge_image_url": "https://img.shields.io/badge/Salesforce-Certified_Admin-00A1E0?style=for-the-badge&logo=salesforce&logoColor=white",
        "exam_cost": 200,
        "estimated_hours": 100,
        "description": "Prove your knowledge of Salesforce applications, configuration, and management.",
        "course_url": "https://www.udemy.com/course/salesforce-administrator/",
        "official_exam_url": "https://trailhead.salesforce.com/en/credentials/administrator"
    }
]

added = 0
for cert_data in certs_to_add:
    existing = db.query(Certification).filter(Certification.title == cert_data["title"]).first()
    if not existing:
        c = Certification(**cert_data)
        db.add(c)
        added += 1
    else:
        # Update badge if it already exists
        existing.badge_image_url = cert_data["badge_image_url"]

db.commit()
print(f"Seeded {added} new certifications and updated existing badges.")
db.close()
