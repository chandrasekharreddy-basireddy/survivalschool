"use client";

import { useAuth } from "@/lib/auth-context";
import { hasRole, isAdmin, isInstructor, isStudent, type AppRole } from "@/lib/roles";

export function useRole() {
  const { user } = useAuth();
  return {
    hasRole: (roles: AppRole | AppRole[]) => hasRole(user, roles),
    hasPermission: (code: string) => user?.roles.some((role) => role === "ADMIN" || role === "SUPER_ADMIN") || false,
    isStudent: isStudent(user),
    isInstructor: isInstructor(user),
    isAdmin: isAdmin(user),
  };
}
