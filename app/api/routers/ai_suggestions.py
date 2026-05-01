from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Dict, Any
from datetime import datetime, timedelta

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.models.enrollment import Enrollment, EnrollmentStatus
from app.models.certification import Certification

router = APIRouter()


@router.get("/certifications")
def get_ai_certification_suggestions(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Get AI-powered certification suggestions based on user profile and progress"""
    
    # Get user's current and completed certifications
    user_enrollments = (
        db.query(Enrollment)
        .filter(Enrollment.user_id == user.id)
        .all()
    )
    
    completed_cert_ids = [
        enrollment.certification_id 
        for enrollment in user_enrollments 
        if enrollment.status == EnrollmentStatus.completed
    ]
    
    current_cert_ids = [
        enrollment.certification_id 
        for enrollment in user_enrollments 
        if enrollment.status in [EnrollmentStatus.selected, EnrollmentStatus.in_progress]
    ]
    
    # Analyze user's certification patterns
    providers_completed = (
        db.query(Certification.provider)
        .filter(Certification.id.in_(completed_cert_ids))
        .distinct()
        .all()
    )
    
    # Get all available certifications excluding user's current ones
    available_certs = (
        db.query(Certification)
        .filter(~Certification.id.in_(current_cert_ids + completed_cert_ids))
        .all()
    )
    
    # AI-like scoring based on user patterns
    suggestions = []
    for cert in available_certs:
        score = 0
        reasons = []
        
        # Boost score if it's from a provider the user has completed before
        if cert.provider in [p[0] for p in providers_completed]:
            score += 30
            reasons.append(f"Same provider as your completed certifications")
        
        # Boost score based on difficulty progression
        completed_count = len(completed_cert_ids)
        if completed_count == 0:
            # Beginner recommendations
            if "beginner" in cert.title.lower() or "fundamentals" in cert.title.lower():
                score += 25
                reasons.append("Good starting point for beginners")
        elif completed_count <= 3:
            # Intermediate recommendations
            if "intermediate" in cert.title.lower() or "advanced" in cert.title.lower():
                score += 20
                reasons.append("Next level in your learning journey")
        else:
            # Advanced recommendations
            if "expert" in cert.title.lower() or "professional" in cert.title.lower():
                score += 25
                reasons.append("Advanced certification for your experience")
        
        # Boost score for popular/trending certifications
        enrollments_count = (
            db.query(func.count(Enrollment.id))
            .filter(Enrollment.certification_id == cert.id)
            .scalar() or 0
        )
        if enrollments_count > 10:
            score += 15
            reasons.append("Popular among learners")
        
        # Boost score for recent certifications
        if cert.created_at and cert.created_at > datetime.now() - timedelta(days=90):
            score += 10
            reasons.append("Recently updated content")
        
        if score > 0:
            suggestions.append({
                "certification": {
                    "id": cert.id,
                    "title": cert.title,
                    "provider": cert.provider,
                    "description": cert.description,
                    "difficulty_level": getattr(cert, 'difficulty_level', 'Intermediate'),
                    "duration_hours": getattr(cert, 'duration_hours', 40),
                    "created_at": cert.created_at
                },
                "score": score,
                "reasons": reasons,
                "match_percentage": min(95, score + 20)  # Simulated match percentage
            })
    
    # Sort by score and return top suggestions
    suggestions.sort(key=lambda x: x["score"], reverse=True)
    
    return {
        "suggestions": suggestions[:10],
        "analysis": {
            "completed_certifications": len(completed_cert_ids),
            "current_enrollments": len(current_cert_ids),
            "preferred_providers": [p[0] for p in providers_completed],
            "skill_level": "Beginner" if len(completed_cert_ids) <= 2 else "Intermediate" if len(completed_cert_ids) <= 5 else "Advanced"
        }
    }


@router.get("/courses/{certification_id}")
def get_course_suggestions(
    certification_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Get course suggestions to fulfill certification requirements"""
    
    certification = (
        db.query(Certification)
        .filter(Certification.id == certification_id)
        .first()
    )
    
    if not certification:
        return {"error": "Certification not found"}
    
    # Simulated course suggestions based on certification content
    # In a real implementation, this would analyze the certification requirements
    base_courses = [
        {
            "id": 1,
            "title": f"Foundations of {certification.provider}",
            "description": "Essential基础知识",
            "duration_hours": 20,
            "difficulty": "Beginner",
            "type": "required"
        },
        {
            "id": 2,
            "title": f"Advanced {certification.title.split()[0]} Concepts",
            "description": "Deep dive into core concepts",
            "duration_hours": 30,
            "difficulty": "Intermediate",
            "type": "required"
        },
        {
            "id": 3,
            "title": f"Practical {certification.title.split()[0]} Projects",
            "description": "Hands-on experience",
            "duration_hours": 25,
            "difficulty": "Intermediate",
            "type": "required"
        }
    ]
    
    # Add elective courses based on user's progress
    user_completed = (
        db.query(func.count(Enrollment.id))
        .filter(
            Enrollment.user_id == user.id,
            Enrollment.status == EnrollmentStatus.completed
        )
        .scalar() or 0
    )
    
    elective_courses = []
    if user_completed > 2:
        elective_courses.append({
            "id": 4,
            "title": "Specialization Topics",
            "description": "Advanced specialization areas",
            "duration_hours": 15,
            "difficulty": "Advanced",
            "type": "elective"
        })
    
    return {
        "certification": {
            "id": certification.id,
            "title": certification.title,
            "provider": certification.provider
        },
        "required_courses": base_courses,
        "elective_courses": elective_courses,
        "total_duration": sum(course["duration_hours"] for course in base_courses + elective_courses),
        "estimated_completion": f"{len(base_courses + elective_courses)} weeks"
    }
