import type { CurrentUser } from "@/lib/auth-context";

export type AppRole = "STUDENT" | "INSTRUCTOR" | "MODERATOR" | "SUPPORT" | "ADMIN" | "SUPER_ADMIN";

export function hasRole(user: CurrentUser | null | undefined, roles: AppRole | AppRole[]) {
  if (!user) return false;
  const allowed = Array.isArray(roles) ? roles : [roles];
  return user.roles.some((role) => allowed.includes(role as AppRole));
}

export function isAdmin(user: CurrentUser | null | undefined) {
  return hasRole(user, ["ADMIN", "SUPER_ADMIN"]);
}

export function isInstructor(user: CurrentUser | null | undefined) {
  return hasRole(user, ["INSTRUCTOR", "ADMIN", "SUPER_ADMIN"]);
}

export function isStudent(user: CurrentUser | null | undefined) {
  return hasRole(user, "STUDENT");
}

export function getPostLoginPath(user: CurrentUser) {
  if (hasRole(user, ["SUPER_ADMIN", "ADMIN"])) return "/admin";
  if (hasRole(user, "INSTRUCTOR")) return "/instructor";
  return "/dashboard";
}
