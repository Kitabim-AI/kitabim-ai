export interface Character {
  id: string;
  name_uy: string;
  name_en: string;
  avatar_emoji: string;
}

export const CHARACTERS: Character[] = [
  {
    id: 'religious_scholar',
    name_uy: 'ئۆلىما',
    name_en: 'Religious Scholar',
    avatar_emoji: '🕌'
  },
  {
    id: 'uyghurologist',
    name_uy: 'ئۇيغۇرشۇناس',
    name_en: 'Uyghurologist',
    avatar_emoji: '👨‍🎓'
  },
  {
    id: 'historian',
    name_uy: 'تارىخشۇناس',
    name_en: 'Historian',
    avatar_emoji: '📜'
  },
  {
    id: 'writer',
    name_uy: 'ئەدىب',
    name_en: 'Writer',
    avatar_emoji: '✒️'
  },
  {
    id: 'librarian',
    name_uy: 'زېرەكچاق',
    name_en: 'Librarian',
    avatar_emoji: '📚'
  }
];

export const DEFAULT_CHARACTER_ID = 'librarian';
