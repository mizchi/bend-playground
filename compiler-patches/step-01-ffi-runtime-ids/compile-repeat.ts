// Exercise compiler-global ID resets within one process, including a JS compile.
import * as path from "node:path";
import { pathToFileURL } from "node:url";

const [repo, source, control] = process.argv.slice(2);
const Bend = await import(pathToFileURL(path.join(repo, "bend2/bend.ts")).href);
const Comp = await import(pathToFileURL(path.join(repo, "bend2/comp.ts")).href);

async function load(file: string) {
  const book = Bend.book_nil();
  await Bend.book_load(book, file, "", new Map());
  Bend.book_valid(book);
  return book;
}

const book = await load(source);
const first = Comp.compile_book(book);
const same = Comp.compile_book(book);
const js = Comp.js_book(await load(control));
const afterJS = Comp.compile_book(book);
const fresh = Comp.compile_book(await load(source));
process.stdout.write(JSON.stringify({
  same_book_equal: first === same,
  c_after_js_equal: first === afterJS,
  fresh_book_equal: first === fresh,
  js_generated: js.length > 0,
}) + "\n");
