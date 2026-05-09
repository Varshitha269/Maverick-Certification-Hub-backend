"""
MCP Server for Maverick Certification Hub
Exposes standard enrollment and verification tools for AI assistants
"""

import asyncio
import json
import sys
from typing import Any, Dict, List, Optional
from pathlib import Path

# Add current directory to Python path for imports
sys.path.append(str(Path(__file__).parent))

try:
    from app.db.session import SessionLocal
    from app.models.certification import Certification
    from app.models.enrollment import Enrollment
    from app.models.user import User
    from app.core.security import hash_password as get_password_hash
    DB_AVAILABLE = True
except Exception as e:
    print(f"Error importing app modules: {e}")
    DB_AVAILABLE = False

# Tool definitions
def _cert_to_dict(cert: Certification, include_details: bool = False) -> Dict[str, Any]:
    result = {
        "id": cert.id,
        "title": cert.title,
        "provider": cert.provider,
        "category": cert.category,
        "level": cert.level,
        "description": cert.description,
        "estimated_hours": cert.estimated_hours,
        "duration": cert.duration,
        "tags": cert.tags,
    }
    if include_details:
        result.update(
            {
                "prerequisites": cert.prerequisites,
                "course_url": cert.course_url,
                "official_exam_url": cert.official_exam_url,
                "resources": _parse_resources(cert.resources_json),
                "exam_cost": cert.exam_cost,
                "badge_image_url": cert.badge_image_url,
            }
        )
    return result


def _parse_resources(resources_json: str | None) -> Any:
    if not resources_json:
        return []
    try:
        return json.loads(resources_json)
    except json.JSONDecodeError:
        return resources_json


def get_available_tools():
    """Define available MCP tools"""
    return [
        {
            "name": "list_certifications",
            "description": "List all available certifications with details",
            "inputSchema": {
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
        },
        {
            "name": "get_certification_details",
            "description": "Get detailed information about a specific certification",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "certification_id": {
                        "type": "integer",
                        "description": "ID of certification"
                    }
                },
                "required": ["certification_id"]
            }
        },
        {
            "name": "enroll_user",
            "description": "Enroll a user in a certification program",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "user_email": {
                        "type": "string",
                        "description": "Email of user to enroll"
                    },
                    "certification_id": {
                        "type": "integer",
                        "description": "ID of certification"
                    },
                    "status": {
                        "type": "string",
                        "enum": ["selected", "in_progress", "saved_for_later"],
                        "description": "Initial enrollment status",
                        "default": "selected"
                    }
                },
                "required": ["user_email", "certification_id"]
            }
        },
        {
            "name": "update_enrollment_status",
            "description": "Update status of a user's enrollment",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "enrollment_id": {
                        "type": "integer",
                        "description": "ID of enrollment"
                    },
                    "status": {
                        "type": "string",
                        "enum": ["selected", "in_progress", "saved_for_later", "completed", "cancelled"],
                        "description": "New status"
                    }
                },
                "required": ["enrollment_id", "status"]
            }
        },
        {
            "name": "verify_certificate_completion",
            "description": "Verify if a user has completed certification requirements",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "user_email": {
                        "type": "string",
                        "description": "Email of user"
                    },
                    "certification_id": {
                        "type": "integer",
                        "description": "ID of certification"
                    }
                },
                "required": ["user_email", "certification_id"]
            }
        },
        {
            "name": "get_user_enrollments",
            "description": "Get all enrollments for a specific user",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "user_email": {
                        "type": "string",
                        "description": "Email of user"
                    }
                },
                "required": ["user_email"]
            }
        },
        {
            "name": "create_user",
            "description": "Create a new user account",
            "inputSchema": {
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
        },
        {
            "name": "get_certification_requirements",
            "description": "Get requirements and study resources for a certification",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "certification_id": {
                        "type": "integer",
                        "description": "ID of certification"
                    }
                },
                "required": ["certification_id"]
            }
        }
    ]

# Tool handlers
def handle_tool_call(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle tool calls"""
    if not DB_AVAILABLE:
        return {
            "content": [{"type": "text", "text": "Database not available"}],
            "isError": True
        }
    
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
            
            result = [_cert_to_dict(cert) for cert in certifications]
            
            return {
                "content": [{"type": "text", "text": json.dumps(result, indent=2)}],
                "isError": False
            }

        elif name == "get_certification_details":
            cert_id = arguments["certification_id"]
            cert = db.query(Certification).filter(Certification.id == cert_id).first()
            
            if not cert:
                return {
                    "content": [{"type": "text", "text": f"Certification with ID {cert_id} not found"}],
                    "isError": True
                }
            
            result = _cert_to_dict(cert, include_details=True)
            
            return {
                "content": [{"type": "text", "text": json.dumps(result, indent=2)}],
                "isError": False
            }

        elif name == "enroll_user":
            user_email = arguments["user_email"]
            cert_id = arguments["certification_id"]
            status = arguments.get("status", "selected")
            
            # Find user
            user = db.query(User).filter(User.email == user_email).first()
            if not user:
                return {
                    "content": [{"type": "text", "text": f"User with email {user_email} not found"}],
                    "isError": True
                }
            
            # Check if certification exists
            cert = db.query(Certification).filter(Certification.id == cert_id).first()
            if not cert:
                return {
                    "content": [{"type": "text", "text": f"Certification with ID {cert_id} not found"}],
                    "isError": True
                }
            
            # Check if already enrolled
            existing = db.query(Enrollment).filter(
                Enrollment.user_id == user.id,
                Enrollment.certification_id == cert_id
            ).first()
            
            if existing:
                return {
                    "content": [{"type": "text", "text": f"User {user_email} is already enrolled in {cert.title}"}],
                    "isError": True
                }
            
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
            
            return {
                "content": [{"type": "text", "text": json.dumps(result, indent=2)}],
                "isError": False
            }

        elif name == "update_enrollment_status":
            enrollment_id = arguments["enrollment_id"]
            new_status = arguments["status"]
            
            enrollment = db.query(Enrollment).filter(Enrollment.id == enrollment_id).first()
            if not enrollment:
                return {
                    "content": [{"type": "text", "text": f"Enrollment with ID {enrollment_id} not found"}],
                    "isError": True
                }
            
            old_status = enrollment.status
            enrollment.status = new_status
            db.commit()
            
            result = {
                "enrollment_id": enrollment.id,
                "old_status": old_status,
                "new_status": new_status,
                "updated_at": enrollment.updated_at.isoformat()
            }
            
            return {
                "content": [{"type": "text", "text": json.dumps(result, indent=2)}],
                "isError": False
            }

        elif name == "verify_certificate_completion":
            user_email = arguments["user_email"]
            cert_id = arguments["certification_id"]
            
            # Find user
            user = db.query(User).filter(User.email == user_email).first()
            if not user:
                return {
                    "content": [{"type": "text", "text": f"User with email {user_email} not found"}],
                    "isError": True
                }
            
            # Find enrollment
            enrollment = db.query(Enrollment).filter(
                Enrollment.user_id == user.id,
                Enrollment.certification_id == cert_id
            ).first()
            
            if not enrollment:
                return {
                    "content": [{"type": "text", "text": f"No enrollment found for user {user_email} in certification {cert_id}"}],
                    "isError": True
                }
            
            result = {
                "user_email": user_email,
                "certification_id": cert_id,
                "is_completed": enrollment.status == "completed",
                "current_status": enrollment.status,
                "enrollment_date": enrollment.created_at.isoformat(),
                "last_updated": enrollment.updated_at.isoformat()
            }
            
            return {
                "content": [{"type": "text", "text": json.dumps(result, indent=2)}],
                "isError": False
            }

        elif name == "get_user_enrollments":
            user_email = arguments["user_email"]
            
            user = db.query(User).filter(User.email == user_email).first()
            if not user:
                return {
                    "content": [{"type": "text", "text": f"User with email {user_email} not found"}],
                    "isError": True
                }
            
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
            
            return {
                "content": [{"type": "text", "text": json.dumps(result, indent=2)}],
                "isError": False
            }

        elif name == "create_user":
            email = arguments["email"]
            password = arguments["password"]
            full_name = arguments.get("full_name")
            role = arguments.get("role", "user")
            
            # Check if user already exists
            existing = db.query(User).filter(User.email == email).first()
            if existing:
                return {
                    "content": [{"type": "text", "text": f"User with email {email} already exists"}],
                    "isError": True
                }
            
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
            
            return {
                "content": [{"type": "text", "text": json.dumps(result, indent=2)}],
                "isError": False
            }

        elif name == "get_certification_requirements":
            cert_id = arguments["certification_id"]
            
            cert = db.query(Certification).filter(Certification.id == cert_id).first()
            if not cert:
                return {
                    "content": [{"type": "text", "text": f"Certification with ID {cert_id} not found"}],
                    "isError": True
                }
            
            result = {
                "certification_id": cert.id,
                "title": cert.title,
                "prerequisites": cert.prerequisites,
                "study_resources": {
                    "primary_course": cert.course_url,
                    "official_exam": cert.official_exam_url,
                    "additional_resources": _parse_resources(cert.resources_json)
                },
                "estimated_hours": cert.estimated_hours,
                "duration": cert.duration
            }
            
            return {
                "content": [{"type": "text", "text": json.dumps(result, indent=2)}],
                "isError": False
            }

        else:
            return {
                "content": [{"type": "text", "text": f"Unknown tool: {name}"}],
                "isError": True
            }

    except Exception as e:
        return {
            "content": [{"type": "text", "text": f"Error: {str(e)}"}],
            "isError": True
        }
    finally:
        db.close()

def get_available_resources():
    """List available resources"""
    return [
        {
            "uri": "certifications://all",
            "name": "All Certifications",
            "description": "Complete list of available certifications",
            "mimeType": "application/json"
        },
        {
            "uri": "certifications://categories",
            "name": "Certification Categories",
            "description": "List of all certification categories",
            "mimeType": "application/json"
        }
    ]

# Simple MCP server implementation
async def main():
    """Run MCP server"""
    print("Maverick Certification Hub MCP Server", file=sys.stderr)
    print("Available tools:", file=sys.stderr)
    for tool in get_available_tools():
        print(f"  - {tool['name']}: {tool['description']}", file=sys.stderr)
    
    # Simple JSON-RPC server for testing
    try:
        while True:
            line = sys.stdin.readline()
            if not line:
                break
                
            try:
                request = json.loads(line.strip())
                method = request.get("method")
                
                if method == "initialize":
                    response = {
                        "jsonrpc": "2.0",
                        "id": request.get("id"),
                        "result": {
                            "protocolVersion": request.get("params", {}).get("protocolVersion", "2024-11-05"),
                            "capabilities": {
                                "tools": {},
                                "resources": {}
                            },
                            "serverInfo": {
                                "name": "maverick-certification-hub",
                                "version": "1.0.0"
                            }
                        }
                    }

                elif method == "notifications/initialized":
                    continue

                elif method == "ping":
                    response = {
                        "jsonrpc": "2.0",
                        "id": request.get("id"),
                        "result": {}
                    }

                elif method == "tools/list":
                    response = {
                        "jsonrpc": "2.0",
                        "id": request.get("id"),
                        "result": {
                            "tools": get_available_tools()
                        }
                    }
                
                elif method == "tools/call":
                    params = request.get("params", {})
                    name = params.get("name")
                    arguments = params.get("arguments", {})
                    
                    result = handle_tool_call(name, arguments)
                    response = {
                        "jsonrpc": "2.0",
                        "id": request.get("id"),
                        "result": result
                    }
                
                elif method == "resources/list":
                    response = {
                        "jsonrpc": "2.0",
                        "id": request.get("id"),
                        "result": {
                            "resources": get_available_resources()
                        }
                    }
                
                else:
                    response = {
                        "jsonrpc": "2.0",
                        "id": request.get("id"),
                        "error": {
                            "code": -32601,
                            "message": f"Method not found: {method}"
                        }
                    }
                
                print(json.dumps(response))
                sys.stdout.flush()
                
            except json.JSONDecodeError:
                error_response = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {
                        "code": -32700,
                        "message": "Parse error"
                    }
                }
                print(json.dumps(error_response))
                sys.stdout.flush()
                
    except KeyboardInterrupt:
        print("\nServer stopped")

if __name__ == "__main__":
    asyncio.run(main())
