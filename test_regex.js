const url = 'ref:df1b002d28bd';
const text = '178، 179 بەت';
const parts = url.split(':');
const bookId = parts[1];
let pageNumsStr = parts.slice(2).join(' ');
if (!pageNumsStr) {
    pageNumsStr = text;
}
const pageNumsMatch = pageNumsStr.match(/\d+/g) || [];
const pageNums = pageNumsMatch.map(p => parseInt(p, 10)).filter(n => !isNaN(n));
console.log(pageNums);
