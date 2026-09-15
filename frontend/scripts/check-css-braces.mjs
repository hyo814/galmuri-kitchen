// styles.css 괄호 짝 검사. 병합에서 `}` 하나가 빠지면(933b6fa) 뒤 규칙이 모두 중첩으로 읽혀 조용히 무효가 되고 빌드도 통과한다.
// ponytail: 주석·문자열만 건너뛰는 괄호 세기, 문법 전체 검사는 stylelint를 들일 때
import { readFileSync } from "node:fs";

export function unclosedLine(css) {
  const stack = [];
  let line = 1;
  for (let i = 0; i < css.length; i++) {
    const c = css[i];
    if (c === "\n") line++;
    else if (c === "/" && css[i + 1] === "*") {
      const end = css.indexOf("*/", i + 2);
      const stop = end < 0 ? css.length : end + 2;
      line += css.slice(i, stop).split("\n").length - 1;
      i = stop - 1;
    } else if (c === '"' || c === "'") {
      const end = css.indexOf(c, i + 1);
      i = end < 0 ? css.length : end;
    } else if (c === "{") stack.push(line);
    else if (c === "}" && stack.pop() === undefined) return line;
  }
  return stack[0] ?? null;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  console.assert(unclosedLine("a {\n}\nb { c { } }") === null);
  console.assert(unclosedLine("a {\n  x: 1;\n\n/* } */\nb { }") === 1);
  console.assert(unclosedLine('a { content: "}"; }') === null);
  console.assert(unclosedLine("a { }\n}") === 2);
  const file = new URL("../src/styles.css", import.meta.url);
  const bad = unclosedLine(readFileSync(file, "utf8"));
  if (bad !== null) {
    console.error(`styles.css ${bad}번째 줄 근처의 { } 짝이 맞지 않아요.`);
    process.exit(1);
  }
}
