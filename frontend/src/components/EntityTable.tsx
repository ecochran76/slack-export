import type { ReactNode } from "react";

export type EntityTableColumn<Row> = {
  header: string;
  id: string;
  render: (row: Row) => ReactNode;
  rowHeader?: boolean;
};

export function EntityTable<Row>({
  ariaLabel,
  columns,
  getRowKey,
  rows
}: {
  ariaLabel: string;
  columns: EntityTableColumn<Row>[];
  getRowKey: (row: Row) => string;
  rows: Row[];
}) {
  return (
    <div className="entity-table-shell" role="region" aria-label={ariaLabel} tabIndex={0}>
      <table className="entity-table">
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column.id} scope="col">
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={getRowKey(row)}>
              {columns.map((column) => {
                const content = column.render(row);
                if (column.rowHeader) {
                  return (
                    <th key={column.id} scope="row">
                      {content}
                    </th>
                  );
                }

                return <td key={column.id}>{content}</td>;
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
