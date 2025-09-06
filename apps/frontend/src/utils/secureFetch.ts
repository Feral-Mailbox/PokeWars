export async function secureFetch(input: string | Request, init?: RequestInit) {
  const isNode = typeof window === "undefined";
  let finalInput: string | Request = input;

  if (typeof input === "string" && input.startsWith("/") && isNode) {
    finalInput = "http://poketactics:3000" + input;
  }

  if (input instanceof Request && isNode && input.url.startsWith("/")) {
    finalInput = new Request("http://poketactics:3000" + input.url, input);
  }

  const res = await fetch(finalInput, init);

  return res;
}
