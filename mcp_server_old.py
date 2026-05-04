"""
MCP Server for Maverick Certification Hub
Exposes standard enrollment and verification tools for AI assistants
"""

import asyncio
import json
from typing import Any, Dict, List, Optional
try:
    from mcp.server import Server
    from mcp.server.models import InitializationOptions
    from mcp.server.stdio import stdio_server
    from mcp.types import (
        CallToolRequest,
        CallToolResult,
        GetPromptRequest,
        GetPromptResult,
        ListPromptsRequest,
        ListPromptsResult,
        ListResourcesRequest,
        ListResourcesResult,
        ListToolsRequest,
        ListToolsResult,
        Prompt,
        Resource,
        Tool,
    )
except ImportError as e:
    print(f"MCP import error: {e}")
    print("Please ensure you have the correct MCP package installed: pip install mcp")
    # Fallback imports for testing
    from dataclasses import dataclass
    from typing import Any, Dict, List, Optional
    
    @dataclass
    class Tool:
        name: str
        description: str
        inputSchema: Dict[str, Any]
    
    @dataclass
    class Resource:
        uri: str
        name: str
        description: str
        mimeType: str
    
    @dataclass
    class CallToolResult:
        content: List[Dict[str, Any]]
        isError: bool = False
    
    @dataclass
    class ListToolsResult:
        tools: List[Tool]
    
    @dataclass
    class ListResourcesResult:
        resources: List[Resource]

from app.db.session import SessionLocal
from app.models.certification import Certification
from app.models.enrollment import Enrollment
from app.models.user import User
from app.core.security import get_password_hash

# Create MCP server instance
try:
    server = Server("maverick-certification-hub")
    
    @server.list_tools()
    async def handle_list_tools() -> List[Tool]:
except Exception as e:
    print(f"Error setting up MCP server: {e}")
    # Fallback simple server for testing
    def handle_list_tools():
    """List available MCP tools"""
    return [
        Tool(
            name="list_certifications",
            description="List all available certifications with details",
            inputSchema={
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Filter by category (optional)"
                    },
                    "level": {
                        "type": "string", 
                        "description": "Filter by level (optional)"
                    }
                }
            }
        ),
        Tool(
            name="get_certification_details",
            description="Get detailed information about a specific certification",
            inputSchema={
                "type": "object",
                "properties": {
                    "certification_id": {
                        "type": "integer",
                        "description": "ID of the certification"
                    }
                },
                "required": ["certification_id"]
            }
        ),
        Tool(
            name="enroll_user",
            description="Enroll a user in a certification program",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_email": {
                        "type": "string",
                        "description": "Email of the user to enroll"
                    },
                    "certification_id": {
                        "type": "integer",
                        "description": "ID of the certification"
                    },
                    "status": {
                        "type": "string",
                        "enum": ["not_started", "in_progress", "saved_for_later"],
                        "description": "Initial enrollment status",
                        "default": "not_started"
                    }
                },
                "required": ["user_email", "certification_id"]
            }
        ),
        Tool(
            name="update_enrollment_status",
            description="Update the status of a user's enrollment",
            inputSchema={
                "type": "object",
                "properties": {
                    "enrollment_id": {
                        "type": "integer",
                        "description": "ID of the enrollment"
                    },
                    "status": {
                        "type": "string",
                        "enum": ["not_started", "in_progress", "saved_for_later", "completed"],
                        "description": "New status"
                    }
                },
                "required": ["enrollment_id", "status"]
            }
        ),
        Tool(
            name="verify_certificate_completion",
            description="Verify if a user has completed certification requirements",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_email": {
                        "type": "string",
                        "description": "Email of the user"
                    },
                    "certification_id": {
                        "type": "integer",
                        "description": "ID of the certification"
                    }
                },
                "required": ["user_email", "certification_id"]
            }
        ),
        Tool(
            name="get_user_enrollments",
            description="Get all enrollments for a specific user",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_email": {
                        "type": "string",
                        "description": "Email of the user"
                    }
                },
                "required": ["user_email"]
            }
        ),
        Tool(
            name="create_user",
            description="Create a new user account",
            inputSchema={
                "type": "object",
                "properties": {
                    "email": {
                        "type": "string",
                        "description": "Email address"
                    },
                    "password": {
                        "type": "string",
                        "description": "Password"
                    },
                    "full_name": {
                        "type": "string",
                        "description": "Full name (optional)"
                    },
                    "role": {
                        "type": "string",
                        "enum": ["user", "admin"],
                        "description": "User role",
                        "default": "user"
                    }
                },
                "required": ["email", "password"]
            }
        ),
        Tool(
            name="get_certification_requirements",
            description="Get requirements and study resources for a certification",
            inputSchema={
                "type": "object",
                "properties": {
                    "certification_id": {
                        "type": "integer",
                        "description": "ID of the certification"
                    }
                },
                "required": ["certification_id"]
            }
        )
    ]

@server.call_tool()
async def handle_call_tool(name: str, arguments: Dict[str, Any]) -> CallToolResult:
    """Handle tool calls"""
    db = SessionLocal()
    try:
        if name == "list_certifications":
            category = arguments.get("category")
            level = arguments.get("level")
            
            query = db.query(Certification)
            if category:
                query = query.filter(Certification.category == category)
            if level:
                query = query.filter(Certification.level == level)
                
            certifications = query.all()
            
            result = [
                {
                    "id": cert.id,
                    "title": cert.title,
                    "provider": cert.provider,
                    "category": cert.category,
                    "level": cert.level,
                    "description": cert.description,
                    "duration_hours": cert.duration_hours,
                    "difficulty": cert.difficulty
                }
                for cert in certifications
            ]
            
            return CallToolResult(
                content=[{"type": "text", "text": json.dumps(result, indent=2)}]
            )

        elif name == "get_certification_details":
            cert_id = arguments["certification_id"]
            cert = db.query(Certification).filter(Certification.id == cert_id).first()
            
            if not cert:
                return CallToolResult(
                    content=[{"type": "text", "text": f"Certification with ID {cert_id} not found"}],
                    isError=True
                )
            
            result = {
                "id": cert.id,
                "title": cert.title,
                "provider": cert.provider,
                "category": cert.category,
                "level": cert.level,
                "description": cert.description,
                "duration_hours": cert.duration_hours,
                "difficulty": cert.difficulty,
                "prerequisites": cert.prerequisites,
                "exam_info": cert.exam_info,
                "course_url": cert.course_url,
                "official_exam_url": cert.official_exam_url,
                "resource_urls": cert.resource_urls
            }
            
            return CallToolResult(
                content=[{"type": "text", "text": json.dumps(result, indent=2)}]
            )

        elif name == "enroll_user":
            user_email = arguments["user_email"]
            cert_id = arguments["certification_id"]
            status = arguments.get("status", "not_started")
            
            # Find user
            user = db.query(User).filter(User.email == user_email).first()
            if not user:
                return CallToolResult(
                    content=[{"type": "text", "text": f"User with email {user_email} not found"}],
                    isError=True
                )
            
            # Check if certification exists
            cert = db.query(Certification).filter(Certification.id == cert_id).first()
            if not cert:
                return CallToolResult(
                    content=[{"type": "text", "text": f"Certification with ID {cert_id} not found"}],
                    isError=True
                )
            
            # Check if already enrolled
            existing = db.query(Enrollment).filter(
                Enrollment.user_id == user.id,
                Enrollment.certification_id == cert_id
            ).first()
            
            if existing:
                return CallToolResult(
                    content=[{"type": "text", "text": f"User {user_email} is already enrolled in {cert.title}"}],
                    isError=True
                )
            
            # Create enrollment
            enrollment = Enrollment(
                user_id=user.id,
                certification_id=cert_id,
                status=status
            )
            db.add(enrollment)
            db.commit()
            
            result = {
                "enrollment_id": enrollment.id,
                "user_email": user_email,
                "certification_title": cert.title,
                "status": status,
                "enrolled_at": enrollment.created_at.isoformat()
            }
            
            return CallToolResult(
                content=[{"type": "text", "text": json.dumps(result, indent=2)}]
            )

        elif name == "update_enrollment_status":
            enrollment_id = arguments["enrollment_id"]
            new_status = arguments["status"]
            
            enrollment = db.query(Enrollment).filter(Enrollment.id == enrollment_id).first()
            if not enrollment:
                return CallToolResult(
                    content=[{"type": "text", "text": f"Enrollment with ID {enrollment_id} not found"}],
                    isError=True
                )
            
            old_status = enrollment.status
            enrollment.status = new_status
            db.commit()
            
            result = {
                "enrollment_id": enrollment.id,
                "old_status": old_status,
                "new_status": new_status,
                "updated_at": enrollment.updated_at.isoformat()
            }
            
            return CallToolResult(
                content=[{"type": "text", "text": json.dumps(result, indent=2)}]
            )

        elif name == "verify_certificate_completion":
            user_email = arguments["user_email"]
            cert_id = arguments["certification_id"]
            
            # Find user
            user = db.query(User).filter(User.email == user_email).first()
            if not user:
                return CallToolResult(
                    content=[{"type": "text", "text": f"User with email {user_email} not found"}],
                    isError=True
                )
            
            # Find enrollment
            enrollment = db.query(Enrollment).filter(
                Enrollment.user_id == user.id,
                Enrollment.certification_id == cert_id
            ).first()
            
            if not enrollment:
                return CallToolResult(
                    content=[{"type": "text", "text": f"No enrollment found for user {user_email} in certification {cert_id}"}],
                    isError=True
                )
            
            result = {
                "user_email": user_email,
                "certification_id": cert_id,
                "is_completed": enrollment.status == "completed",
                "current_status": enrollment.status,
                "enrollment_date": enrollment.created_at.isoformat(),
                "last_updated": enrollment.updated_at.isoformat()
            }
            
            return CallToolResult(
                content=[{"type": "text", "text": json.dumps(result, indent=2)}]
            )

        elif name == "get_user_enrollments":
            user_email = arguments["user_email"]
            
            user = db.query(User).filter(User.email == user_email).first()
            if not user:
                return CallToolResult(
                    content=[{"type": "text", "text": f"User with email {user_email} not found"}],
                    isError=True
                )
            
            enrollments = db.query(Enrollment).filter(Enrollment.user_id == user.id).all()
            
            result = []
            for enrollment in enrollments:
                cert = db.query(Certification).filter(Certification.id == enrollment.certification_id).first()
                result.append({
                    "enrollment_id": enrollment.id,
                    "certification": {
                        "id": cert.id,
                        "title": cert.title,
                        "provider": cert.provider,
                        "category": cert.category,
                        "level": cert.level
                    } if cert else None,
                    "status": enrollment.status,
                    "enrolled_at": enrollment.created_at.isoformat(),
                    "updated_at": enrollment.updated_at.isoformat()
                })
            
            return CallToolResult(
                content=[{"type": "text", "text": json.dumps(result, indent=2)}]
            )

        elif name == "create_user":
            email = arguments["email"]
            password = arguments["password"]
            full_name = arguments.get("full_name")
            role = arguments.get("role", "user")
            
            # Check if user already exists
            existing = db.query(User).filter(User.email == email).first()
            if existing:
                return CallToolResult(
                    content=[{"type": "text", "text": f"User with email {email} already exists"}],
                    isError=True
                )
            
            # Create user
            user = User(
                email=email,
                hashed_password=get_password_hash(password),
                full_name=full_name,
                role=role,
                is_active=True
            )
            db.add(user)
            db.commit()
            
            result = {
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "role": user.role,
                "is_active": user.is_active,
                "created_at": user.created_at.isoformat()
            }
            
            return CallToolResult(
                content=[{"type": "text", "text": json.dumps(result, indent=2)}]
            )

        elif name == "get_certification_requirements":
            cert_id = arguments["certification_id"]
            
            cert = db.query(Certification).filter(Certification.id == cert_id).first()
            if not cert:
                return CallToolResult(
                    content=[{"type": "text", "text": f"Certification with ID {cert_id} not found"}],
                    isError=True
                )
            
            result = {
                "certification_id": cert.id,
                "title": cert.title,
                "prerequisites": cert.prerequisites,
                "exam_info": cert.exam_info,
                "study_resources": {
                    "primary_course": cert.course_url,
                    "official_exam": cert.official_exam_url,
                    "additional_resources": cert.resource_urls
                },
                "estimated_duration_hours": cert.duration_hours,
                "difficulty_level": cert.difficulty
            }
            
            return CallToolResult(
                content=[{"type": "text", "text": json.dumps(result, indent=2)}]
            )

        else:
            return CallToolResult(
                content=[{"type": "text", "text": f"Unknown tool: {name}"}],
                isError=True
            )

    except Exception as e:
        return CallToolResult(
            content=[{"type": "text", "text": f"Error: {str(e)}"}],
            isError=True
        )
    finally:
        db.close()

@server.list_resources()
async def handle_list_resources() -> ListResourcesResult:
    """List available resources"""
    return ListResourcesResult(
        resources=[
            Resource(
                uri="certifications://all",
                name="All Certifications",
                description="Complete list of available certifications",
                mimeType="application/json"
            ),
            Resource(
                uri="certifications://categories",
                name="Certification Categories",
                description="List of all certification categories",
                mimeType="application/json"
            )
        ]
    )

async def main():
    """Run the MCP server"""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="maverick-certification-hub",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=None,
                    experimental_capabilities=None,
                )
            )
        )

if __name__ == "__main__":
    asyncio.run(main())
