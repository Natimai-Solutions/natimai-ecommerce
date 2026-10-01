import en from './en';
import fr, { type MessageSchema } from './fr';

export type { MessageSchema };

const messages: Record<'fr' | 'en', MessageSchema> = { fr, en };

export default messages;
