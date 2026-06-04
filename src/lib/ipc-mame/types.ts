export interface ProgressNotification {
  value: number;
  message: string;
  current?: number;
  total?: number;
  stage?: string;
}
