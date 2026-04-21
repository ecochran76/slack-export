import { OperatorShell } from "./components/OperatorShell";
import { TenantWorkbench } from "./features/tenants/TenantWorkbench";

export function App() {
  return (
    <OperatorShell
      account={{ label: "Operator", detail: "local session" }}
      activeSection="Tenants"
      sections={["Tenants", "Search", "Reports", "Logs"]}
    >
      <TenantWorkbench />
    </OperatorShell>
  );
}
