import type { ReactNode } from "react";
import { RoleGate } from "@/components/RoleGate";

export default function InstructorLayout({ children }: { children: ReactNode }) {
  return <RoleGate roles={["INSTRUCTOR", "ADMIN", "SUPER_ADMIN"]}>{children}</RoleGate>;
}
