import type { ReactNode } from "react";
import { RoleGate } from "@/components/RoleGate";

export default function AdminLayout({ children }: { children: ReactNode }) {
  return <RoleGate roles={["ADMIN", "SUPER_ADMIN"]}>{children}</RoleGate>;
}
