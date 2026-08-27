import { describe, expect, it } from 'vitest';
import {
  formatQuranAyahNumber,
  formatQuranAyahUg,
  normalizeArabic,
  normalizeArabicWithAyah,
  toEasternArabicDigits,
} from '../../utils/quranUtils';

describe('quranUtils', () => {
  describe('formatQuranAyahUg', () => {
    it('returns empty string for falsy/empty input', () => {
      expect(formatQuranAyahUg('')).toBe('');
      expect(formatQuranAyahUg('   ')).toBe('');
    });

    it('adds a period to ayahs without terminal punctuation', () => {
      expect(formatQuranAyahUg('ناھايىتى شەپقەتلىك ۋە مېھرىبان ئاللاھنىڭ ئىسمى بىلەن باشلايمەن'))
        .toBe('ناھايىتى شەپقەتلىك ۋە مېھرىبان ئاللاھنىڭ ئىسمى بىلەن باشلايمەن.');
      expect(formatQuranAyahUg('جىمى ھەمدۇ سانا ئالەملەرنىڭ پەرۋەردىگارى ئاللاھقا خاستۇر'))
        .toBe('جىمى ھەمدۇ سانا ئالەملەرنىڭ پەرۋەردىگارى ئاللاھقا خاستۇر.');
    });

    it('preserves existing period at the end', () => {
      expect(formatQuranAyahUg('بەلكى لەۋھۇلمەھپۇزدا ساقلانغان ئۇلۇغ قۇرئاندۇر.'))
        .toBe('بەلكى لەۋھۇلمەھپۇزدا ساقلانغان ئۇلۇغ قۇرئاندۇر.');
    });

    it('preserves Uyghur and Arabic question marks without adding a period', () => {
      expect(formatQuranAyahUg('ئۇلار (ئاللاھنىڭ قۇدرىتىگە) ئىشەنمەمدۇ؟'))
        .toBe('ئۇلار (ئاللاھنىڭ قۇدرىتىگە) ئىشەنمەمدۇ؟');
      expect(formatQuranAyahUg('سائادەتمەنلەر قانداق ئادەملەر?'))
        .toBe('سائادەتمەنلەر قانداق ئادەملەر?');
    });

    it('preserves exclamation marks without adding a period', () => {
      expect(formatQuranAyahUg('جىمى ھەمدۇسانا ئالەملەرنىڭ پەرۋەردىگارى ئاللاھقا خاستۇر!'))
        .toBe('جىمى ھەمدۇسانا ئالەملەرنىڭ پەرۋەردىگارى ئاللاھقا خاستۇر!');
    });

    it('handles ayahs ending with parentheses', () => {
      expect(formatQuranAyahUg('سەن ئىنئام قىلغانلارنىڭ يولىغا (باشلىغىن)'))
        .toBe('سەن ئىنئام قىلغانلارنىڭ يولىغا (باشلىغىن).');
      expect(formatQuranAyahUg('سەن ئىنئام قىلغانلارنىڭ يولىغا (باشلىغىن!)'))
        .toBe('سەن ئىنئام قىلغانلارنىڭ يولىغا (باشلىغىن!)');
    });

    it('handles ayahs ending with quotation marks', () => {
      expect(formatQuranAyahUg('ئۇلار (تەۋھىد) تىن يۈز ئۆرۈگۈچىلەردۇر»'))
        .toBe('ئۇلار (تەۋھىد) تىن يۈز ئۆرۈگۈچىلەردۇر.»');
      expect(formatQuranAyahUg('ئۇلار: «ئى ئىبراھىم! بۇتلىرىمىزنى مۇشۇنداق قىلغان سەنمۇ؟»'))
        .toBe('ئۇلار: «ئى ئىبراھىم! بۇتلىرىمىزنى مۇشۇنداق قىلغان سەنمۇ؟»');
    });

    it('removes trailing verse numbering artifacts and adds period properly', () => {
      expect(formatQuranAyahUg('ئۇلار: «ئى ئىبراھىم! بۇتلىرىمىزنى مۇشۇنداق قىلغان سەنمۇ؟» دېدى.(62)'))
        .toBe('ئۇلار: «ئى ئىبراھىم! بۇتلىرىمىزنى مۇشۇنداق قىلغان سەنمۇ؟» دېدى.');
      expect(formatQuranAyahUg('كاپىرلار مەسخىرە قىلغان قىلمىشلىرىنىڭ جازاسىنى تارتتىمۇ؟(36)'))
        .toBe('كاپىرلار مەسخىرە قىلغان قىلمىشلىرىنىڭ جازاسىنى تارتتىمۇ؟');
      expect(formatQuranAyahUg('يامغۇرلۇق بۇلۇت بىلەن قەسەمكى(11)،'))
        .toBe('يامغۇرلۇق بۇلۇت بىلەن قەسەمكى.');
      expect(formatQuranAyahUg('ھېكمەتلىك قۇرئان بىلەن قەسەمكى (2)'))
        .toBe('ھېكمەتلىك قۇرئان بىلەن قەسەمكى.');
    });

    it('strips trailing commas and ensures period', () => {
      expect(formatQuranAyahUg('قۇرئاننى ساڭا سېنى جاپاغا سېلىش ئۈچۈن ئەمەس،'))
        .toBe('قۇرئاننى ساڭا سېنى جاپاغا سېلىش ئۈچۈن ئەمەس.');
    });
  });

  describe('toEasternArabicDigits', () => {
    it('converts western digits to eastern arabic-indic digits', () => {
      expect(toEasternArabicDigits(1)).toBe('١');
      expect(toEasternArabicDigits(62)).toBe('٦٢');
      expect(toEasternArabicDigits(114)).toBe('١١٤');
      expect(toEasternArabicDigits('255')).toBe('٢٥٥');
    });
  });

  describe('formatQuranAyahNumber', () => {
    it('formats ayah number enclosed in ornate Quranic brackets (﴿...﴾)', () => {
      expect(formatQuranAyahNumber(1)).toBe('\uFD3F١\uFD3E');
      expect(formatQuranAyahNumber(7)).toBe('\uFD3F٧\uFD3E');
      expect(formatQuranAyahNumber(286)).toBe('\uFD3F٢٨٦\uFD3E');
    });
  });

  describe('normalizeArabicWithAyah', () => {
    it('appends formatted Quranic ayah number to normalized Arabic text', () => {
      expect(normalizeArabicWithAyah('بِسۡمِ ٱللَّهِ ٱلرَّحۡمَٰنِ ٱلرَّحِيمِ', 1))
        .toBe('بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ \uFD3F١\uFD3E');
    });

    it('handles empty text gracefully', () => {
      expect(normalizeArabicWithAyah('', 1)).toBe('');
    });
  });

  describe('normalizeArabic', () => {
    it('returns empty string for empty input', () => {
      expect(normalizeArabic('')).toBe('');
    });

    it('converts Uthmanic Sukun and Alif Wasla to standard forms', () => {
      const uthmanic = '\u0671\u0644\u0652\u062D\u064E\u0645\u0652\u062F\u064F \u0644\u0650\u0644\u0651\u064E\u0647\u0650';
      const normalized = normalizeArabic(uthmanic);
      expect(normalized).not.toContain('\u0671');
      expect(normalized).toContain('\u0627');
    });
  });
});
