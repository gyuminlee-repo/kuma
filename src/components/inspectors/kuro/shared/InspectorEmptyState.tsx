/**
 * InspectorEmptyState — fallback when no row is selected or data is absent.
 */

type InspectorEmptyStateProps = {
  message: string;
};

export function InspectorEmptyState({ message }: InspectorEmptyStateProps) {
  return (
    <p className="text-caption text-muted-foreground">{message}</p>
  );
}
