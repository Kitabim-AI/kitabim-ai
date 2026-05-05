import { useEffect } from 'react';

// Global state for Uyghur input
let imode = 0; // 0 for Uyghur, 1 for English
let qmode = 0; // 0 for opening quote, 1 for closing

const km = new Array(128).fill(0);
const cm = new Array(256).fill(0);

const PRIMe = 233;
const PRIME = 201;
const COLo = 246;
const COLO = 214;
const COLu = 252;
const COLU = 220;
const HAMZA = 0x0626;
const CHEE = 0x0686;
const GHEE = 0x063A;
const NGEE = 0x06AD;
const SHEE = 0x0634;
const SZEE = 0x0698;

const OQUOTE = 0x00AB;
const CQUOTE = 0x00BB;
const RCQUOTE = 0x2019;

function gac(ascii: string) {
  return ascii.charCodeAt(0);
}

function gas(code: number) {
  return String.fromCharCode(code);
}

let inited = false;

function bedit_init() {
  if (inited) return;
  inited = true;

  // Uyghur Unicode character map
  km[gac('a')] = 0x06BE;
  km[gac('b')] = 0x0628;
  km[gac('c')] = 0x063A;
  km[gac('D')] = 0x0698;
  km[gac('d')] = 0x062F;
  km[gac('e')] = 0x06D0;
  km[gac('F')] = 0x0641;
  km[gac('f')] = 0x0627;
  km[gac('G')] = 0x06AF;
  km[gac('g')] = 0x06D5;
  km[gac('H')] = 0x062E;
  km[gac('h')] = 0x0649;
  km[gac('i')] = 0x06AD;
  km[gac('J')] = 0x062C;
  km[gac('j')] = 0x0642;
  km[gac('K')] = 0x06C6;
  km[gac('k')] = 0x0643;
  km[gac('l')] = 0x0644;
  km[gac('m')] = 0x0645;
  km[gac('n')] = 0x0646;
  km[gac('o')] = 0x0648;
  km[gac('p')] = 0x067E;
  km[gac('q')] = 0x0686;
  km[gac('r')] = 0x0631;
  km[gac('s')] = 0x0633;
  km[gac('T')] = 0x0640; // space filler character
  km[gac('t')] = 0x062A;
  km[gac('u')] = 0x06C7;
  km[gac('v')] = 0x06C8;
  km[gac('w')] = 0x06CB;
  km[gac('x')] = 0x0634;
  km[gac('y')] = 0x064A;
  km[gac('z')] = 0x0632;
  km[gac('/')] = 0x0626;

  for (let i = 0; i < km.length; i++) {
    if (km[i] !== 0) {
      const u = gac(gas(i).toUpperCase());
      if (km[u] === 0) {
        km[u] = km[i];
      }
    }
  }

  // Uyghur punctuation marks
  km[gac(';')] = 0x061B;
  km[gac('?')] = 0x061F;
  km[gac(',')] = 0x060C;
  km[gac('<')] = 0x203A; // for '‹'
  km[gac('>')] = 0x2039; // for '›'
  km[gac('"')] = OQUOTE;

  // adapt parens, brackets, and braces for right-to-left typing
  km[gac('{')] = gac('}');
  km[gac('}')] = gac('{');
  km[gac('[')] = gac(']');
  km[gac(']')] = gac('[');
  km[gac('(')] = gac(')');
  km[gac(')')] = gac('(');

  // special handling of braces ( "{" and "}" ) for quotation in Uyghur
  km[gac('}')] = 0x00AB;
  km[gac('{')] = 0x00BB;
}

// React specific insert text function
function insertText(target: HTMLInputElement | HTMLTextAreaElement, text: string) {
  // Use React Native value setter to ensure React's onChange is fired
  const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
    window.HTMLInputElement.prototype,
    'value'
  )?.set;
  const nativeTextAreaValueSetter = Object.getOwnPropertyDescriptor(
    window.HTMLTextAreaElement.prototype,
    'value'
  )?.set;

  const start = target.selectionStart || 0;
  const end = target.selectionEnd || 0;
  const value = target.value;
  const newValue = value.substring(0, start) + text + value.substring(end);

  if (target instanceof HTMLInputElement && nativeInputValueSetter) {
    nativeInputValueSetter.call(target, newValue);
  } else if (target instanceof HTMLTextAreaElement && nativeTextAreaValueSetter) {
    nativeTextAreaValueSetter.call(target, newValue);
  } else {
    target.value = newValue; // fallback
  }

  target.selectionStart = target.selectionEnd = start + text.length;

  const event = new Event('input', { bubbles: true });
  target.dispatchEvent(event);
}

function handleKeyDown(e: KeyboardEvent) {
  const target = e.target as HTMLElement;
  if (!target || (target.tagName !== 'INPUT' && target.tagName !== 'TEXTAREA')) return;
  if (target.tagName === 'INPUT' && (target as HTMLInputElement).type !== 'text' && (target as HTMLInputElement).type !== 'search') return;

  // Ctrl+K to toggle Uyghur/English mode
  if (e.ctrlKey && e.key.toLowerCase() === 'k') {
    e.preventDefault();
    imode = 1 - imode;
    return;
  }

  if (!inited) bedit_init();

  if (!e.ctrlKey && !e.metaKey && !e.altKey && imode === 0) {
    const k = e.key;
    if (k.length !== 1) return; // Ignore modifier keys, arrows, etc.

    const charCode = gac(k);
    if (charCode < km.length && km[charCode] !== 0) {
      e.preventDefault();
      
      let charToInsert = gas(km[charCode]);
      if (charCode === gac('"')) {
        charToInsert = gas(qmode ? OQUOTE : CQUOTE);
        qmode = 1 - qmode;
      }
      
      insertText(target as HTMLInputElement | HTMLTextAreaElement, charToInsert);
    }
  }
}

export function useUyghurInput() {
  useEffect(() => {
    // Add event listener using capture phase to catch them before they reach the inputs
    document.addEventListener('keydown', handleKeyDown, true);
    
    return () => {
      document.removeEventListener('keydown', handleKeyDown, true);
    };
  }, []);
}
