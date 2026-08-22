export type MessageType = 'success' | 'error' | 'warning' | 'info' | 'confirmation';

export type MessageAction = {
  label: string;
  variant?: 'default' | 'destructive' | 'outline';
  onClick: () => void | Promise<void>;
};

export type GlobalMessage = {
  type: MessageType;
  title?: string;
  message: string;
  actions?: MessageAction[];
  dismissible?: boolean;
};

let publish: ((message: GlobalMessage) => void) | null = null;

export function registerMessagePublisher(next: ((message: GlobalMessage) => void) | null) {
  publish = next;
}

export function showMessage(message: GlobalMessage) {
  if (publish) publish(message);
  else console.warn('[message]', message.type, message.message);
}

/** Compatibility API for existing operation feedback. Messages never auto-dismiss. */
export const toast = {
  success: (message: string) => showMessage({ type: 'success', message }),
  error: (message: string) => showMessage({ type: 'error', message }),
  warning: (message: string) => showMessage({ type: 'warning', message }),
  info: (message: string) => showMessage({ type: 'info', message }),
};
