export async function onRequestGet(context) {
  const list = await context.env.REFS.list();
  const out = {};
  for (const k of list.keys) {
    out[k.name] = parseInt((await context.env.REFS.get(k.name)) || '0', 10);
  }
  return new Response(JSON.stringify(out, null, 2) + '\n', { headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' } });
}
