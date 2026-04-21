import { OperatorShell } from "./components/OperatorShell";
import { SelectedResultWorkbench } from "./features/selected-results/SelectedResultWorkbench";

export function App() {
  return (
    <OperatorShell
      account={{ label: "Operator", detail: "local session" }}
      activeSection="Search"
      sections={["Tenants", "Search", "Reports", "Logs"]}
    >
      <SelectedResultWorkbench />
    </OperatorShell>
  );
}
