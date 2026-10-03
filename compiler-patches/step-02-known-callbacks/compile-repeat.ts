import * as path from "node:path";
import { pathToFileURL } from "node:url";
const [repo, source] = process.argv.slice(2);
const B = await import(pathToFileURL(path.join(repo, "bend2/bend.ts")).href);
const C = await import(pathToFileURL(path.join(repo, "bend2/comp.ts")).href);
const load = async () => {
  const book = B.book_nil();
  await B.book_load(book, source, "", new Map()); B.book_valid(book);
  return book;
};
const book = await load();
const entries = Object.entries(book.tlds);
const js = C.js_book(book);
const first = C.compile_book(book);
if (first !== C.compile_book(book)) throw new Error("same book changed");
if (js !== C.js_book(book)) throw new Error("C mutated JS input");
if (first !== C.compile_book(book)) throw new Error("JS polluted C");
if (first !== C.compile_book(await load())) throw new Error("fresh book changed");
if (entries.length !== Object.keys(book.tlds).length || entries.some(([k, d]) => book.tlds[k] !== d))
  throw new Error("caller book was mutated");
console.log("repeat and immutable book: PASS");
