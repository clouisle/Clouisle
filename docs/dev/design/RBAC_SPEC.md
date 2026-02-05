# RBAC Permission System Design Specification

## 1. Overview
This document outlines the Role-Based Access Control (RBAC) system for the Clouisle platform. The system is designed to manage user authentication, authorization, and resource access control in a distributed enterprise environment.

## 2. Core Concepts

- **User**: An entity (person or service account) that interacts with the system.
- **Role**: A collection of permissions. Users are assigned roles.
- **Permission**: A specific right to perform an action on a resource (e.g., `document:read`, `user:delete`).
- **Resource**: The object being accessed (e.g., Knowledge Base, Document, Agent).

## 3. Data Models (Tortoise ORM)

### 3.1 User
Represents the system users.
- `id`: UUID (Primary Key)
- `username`: String (Unique)
- `email`: String (Unique)
- `hashed_password`: String
- `is_active`: Boolean
- `is_superuser`: Boolean (Bypasses all permission checks)
- `created_at`: Datetime
- `last_login`: Datetime
- `department_id`: String (Reserved for future Department/Group feature)
- `auth_source`: String (Default: "local". Options: "ldap", "oidc", "github", etc.)
- `external_id`: String (ID from external auth provider, nullable)
- `avatar_url`: String (User avatar URL, nullable)
- `roles`: Many-to-Many relationship with `Role`

### 3.2 Role
Represents a set of permissions.
- `id`: UUID
- `name`: String (Unique, e.g., "admin", "editor")
- `description`: String
- `is_system_role`: Boolean (Cannot be deleted/modified if True)
- `permissions`: Many-to-Many relationship with `Permission`

### 3.3 Permission
Represents a granular access right.
- `id`: UUID
- `scope`: String (e.g., "knowledge_base", "system", "users")
- `code`: String (Unique, e.g., "kb:create", "user:manage")
- `description`: String

### 3.4 Relationships
- **User-Role**: A user can have multiple roles.
- **Role-Permission**: A role can have multiple permissions.

## 4. Default Roles & Permissions

### 4.1 System Roles
These roles are initialized during the system cold start.

| Role Name | Description | Key Permissions |
| :--- | :--- | :--- |
| **Super Admin** | Full system control | `*` (All permissions) |
| **System Admin** | Manages system config & users | `user:manage`, `system:config`, `audit:view` |
| **Knowledge Manager** | Manages knowledge bases | `kb:create`, `kb:delete`, `kb:manage`, `agent:manage` |
| **Content Creator** | Can create/edit content | `doc:create`, `doc:edit`, `kb:read` |
| **Viewer** | Read-only access | `kb:read`, `doc:read`, `agent:use` |

### 4.2 Permission Scopes (Examples)

- **User Management**: `user:create`, `user:read`, `user:update`, `user:delete`, `user:assign_role`
- **Knowledge Base**: `kb:create`, `kb:read`, `kb:update`, `kb:delete`, `kb:import`
- **Document**: `doc:create`, `doc:read`, `doc:update`, `doc:delete`, `doc:vectorize`
- **Agent**: `agent:create`, `agent:read`, `agent:update`, `agent:delete`, `agent:execute`
- **System**: `system:settings`, `system:logs`
Functional Requirements

### 5.1 Authentication & Session
- **Login**: Authenticate via Username/Password, return JWT Access Token.
- **Logout**: Client-side token discard; Server-side blacklist (optional, via Redis) for immediate revocation.
- **Token Refresh**: Mechanism to refresh expired access tokens.

### 5.2 User Management
- **CRUD Operations**: Create, Read, Update, Delete users.
- **Status Management**: Enable/Disable users (`is_active` flag). Disabled users cannot login.
- **Role Assignment**: Assign one or multiple roles to a user.
- **Department Reservation**: Field reserved for linking users to organizational structures.

### 5.3 Role & Permission Management
- **Role CRUD**: Create custom roles, edit descriptions, delete non-system roles.
- **Permission Assignment**: Grant/Revoke permissions for a Role.
- **Permission Listing**: View all available system permissions.

## 6. Implementation Strategy

### 6
### 5.1 Authentication
- **Protocol**: OAuth2 with Password Flow (Bearer Token).
- **Token**: JWT (JSON Web Token) containing `sub` (user_id) and potentially `scopes` (roles/permissions) for stateless verification, or just `sub` with DB lookup for stateful/revocable checks.

### 5.2 Authorization (FastAPI)
- **Dependency Injection**: Create a `PermissionChecker` class.
  ```python
  # Usage in API routes
  @router.post("/users", dependencies=[Depends(PermissionChecker("user:create"))])
  async def create_user(user: UserCreate):
      ...
  ```
- **Logic**:
  1. Verify JWT.
  2. Fetch User and associated Roles/Permissions (cached in Redis for performance).
  3. Check if User has the required Permission.

### 5.3 Cold Start / Migration
- On application startup, check if the `Permission` table is populated.
- If empty, seed all defined Permissions.
- Check if default `Role`s exist.
- If empty, seed default Roles and associate Permissions.
- Ensure a default `Super Admin` user exists (or prompt to create one via CLI/Env vars).

## 6. Future Considerations
- **Row-Level Security (RLS)**: For multi-tenant or private knowledge bases, we will need to add an `owner_id` or `workspace_id` to resources and check ownership in addition to RBAC.
- **Group/Department**: Add a `Group` model to assign roles to groups of users.
