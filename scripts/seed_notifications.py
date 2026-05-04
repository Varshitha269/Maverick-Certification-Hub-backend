import sys
sys.path.insert(0, '.')
from app.db.session import SessionLocal
from app.models.notification import Notification, NotificationType
from app.models.user import User

db = SessionLocal()
user = db.query(User).filter_by(email='varshithagovindaswamy@gmail.com').first()
if not user:
    user = db.query(User).first()

if user:
    # Clear existing
    db.query(Notification).filter_by(user_id=user.id).delete()
    
    n1 = Notification(
        user_id=user.id,
        type=NotificationType.enrollment,
        title='Application Approved',
        message='Your application for AWS Solutions Architect Associate has been approved by the admin team.',
    )
    n2 = Notification(
        user_id=user.id,
        type=NotificationType.voucher,
        title='Voucher Assigned',
        message='Exam voucher AWS-2026-XXXX-1234 has been assigned for your AWS Solutions Architect certification.',
    )
    n3 = Notification(
        user_id=user.id,
        type=NotificationType.reminder,
        title='Task Deadline Approaching',
        message='Your task "Complete AWS Prerequisites Assessment" is due in 3 days (May 5, 2026).',
    )
    n4 = Notification(
        user_id=user.id,
        type=NotificationType.system,
        title='AI Suggestion Alert',
        message='Based on your progress, AI suggests you apply for the Microsoft Azure Fundamentals AZ-900 certification.',
    )
    
    db.add_all([n1, n2, n3, n4])
    db.commit()
    print('Inserted mock notifications for UI test')
db.close()
