import ugTranslations from '../locales/ug.json';
import enTranslations from '../locales/en.json';

export type Language = 'ug' | 'en';

export const translations = {
  ug: ugTranslations,
  en: enTranslations,
};

export const defaultLanguage: Language = 'ug';

export function getNestedTranslation(obj: any, path: string): string {
  return path.split('.').reduce((current, key) => current?.[key], obj) || path;
}
