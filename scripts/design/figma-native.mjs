/** Emit Figma Plugin API code from a serialized browser scene.
 * Execute the emitted code with use_figma, once per page. Main frame IDs survive.
 */
import crypto from "node:crypto";

export function squash(n, root = false) {
  if (n.key && !root)
    return {
      type: "instance",
      key: n.key,
      x: n.x,
      y: n.y,
      width: n.width,
      height: n.height,
      name: n.name,
    };
  const out = {};
  for (const [key, value] of Object.entries(n)) {
    if (key === "component") continue;
    if (key === "borders" && !value.some((b) => b.width > 0)) continue;
    if (
      (key === "opacity" && value === 1) ||
      (key === "clip" && !value) ||
      (key === "radius" && value === 0) ||
      value === null ||
      value === false
    )
      continue;
    if (key === "children") {
      if (value.length) out.children = value.map((c) => squash(c));
      continue;
    }
    if (key === "svg") {
      out.svg = value.replace(/<([^ >]+)([^>]*)>/g, (tag, kind) =>
        kind === "text" || kind === "tspan"
          ? tag
          : tag.replace(/ font-(?:family|size)="[^"]*"/g, ""),
      );
      continue;
    }
    out[key] =
      typeof value === "number" ? Math.round(value * 100) / 100 : value;
  }
  return out;
}

export function prepareScene(scene) {
  const definitions = new Map();
  function walk(n) {
    for (const child of n.children || []) walk(child);
    if (n.component) {
      const signature = JSON.stringify({ ...n, x: 0, y: 0, key: undefined });
      n.key = crypto
        .createHash("sha256")
        .update(signature)
        .digest("hex")
        .slice(0, 12);
      definitions.set(n.key, n);
    }
  }
  walk(scene.tree);
  return { scene, definitions: [...definitions.values()] };
}

export const nativeRuntime = `
const variables=await figma.variables.getLocalVariablesAsync();
const collections=await figma.variables.getLocalVariableCollectionsAsync();
const ui=collections.find(c=>c.name==='Ninna / UI');
const colors=new Map(variables.filter(v=>v.variableCollectionId===ui.id).map(v=>[v.name,v]));
const numeric=new Map(variables.filter(v=>v.resolvedType==='FLOAT').map(v=>[v.name,v]));
const modes={vallum:ui.modes.find(m=>m.name==='Vallum').modeId,abyssus:ui.modes.find(m=>m.name==='Abyssus').modeId};
const styles=new Map((await figma.getLocalTextStylesAsync()).map(s=>[s.name,s]));
const componentIds=config.components || {};
const componentNodes=new Map();
await Promise.all(Object.entries(componentIds).map(async([key,id])=>{const n=await figma.getNodeByIdAsync(id);if(n?.type==='COMPONENT')componentNodes.set(key,n);}));
const slots={};
const fonts=new Map();
function collectFonts(n){if(n.type==='text')fonts.set(JSON.stringify(n.font),n.font);for(const c of n.children||[])collectFonts(c);}
for(const n of data)collectFonts(n);
await Promise.all([...fonts.values()].map(f=>figma.loadFontAsync(f)));
function color(p){if(!p)return [];const v=colors.get(p.role);if(!v)throw new Error('Missing role '+p.role);return [figma.variables.setBoundVariableForPaint({type:'SOLID',color:(v.resolveForConsumer(figma.currentPage).value),opacity:p.opacity??1},'color',v)];}
function size(n,d){n.resize(Math.max(.1,d.width),Math.max(.1,d.height));n.x=d.x||0;n.y=d.y||0;n.name=d.name||d.type;}
function radius(n,value){n.cornerRadius=Math.min(value||0,Math.min(n.width,n.height)/2);const match=[6,8,12].includes(value)?numeric.get('radius/'+({6:'sm',8:'md',12:'lg'}[value])):null;if(match)for(const field of ['topLeftRadius','topRightRadius','bottomLeftRadius','bottomRightRadius'])n.setBoundVariable(field,match);}
async function build(d,parent,rootComponent=false){
 if(d.type==='group'){for(const c of d.children||[])await build(c,parent);return null;}
 if(d.key&&!rootComponent&&componentNodes.has(d.key)){const n=componentNodes.get(d.key).createInstance();parent.appendChild(n);size(n,d);return n;}
 if(d.type==='text'){
  const n=figma.createText();parent.appendChild(n);n.fontName=d.font;n.fontSize=d.size;n.characters=d.text;
  n.lineHeight={unit:'PIXELS',value:d.lineHeight};n.letterSpacing={unit:'PIXELS',value:d.letterSpacing};
  const styleName='Ninna / UI / '+[d.font.family,d.font.style,d.size,d.lineHeight,d.letterSpacing||0].join(' / ');
  let style=styles.get(styleName);if(!style){style=figma.createTextStyle();style.name=styleName;style.fontName=d.font;style.fontSize=d.size;style.lineHeight=n.lineHeight;style.letterSpacing={unit:'PIXELS',value:d.letterSpacing||0};styles.set(styleName,style);}
  await n.setTextStyleIdAsync(style.id);n.textAutoResize='NONE';size(n,{...d,width:d.width+2,height:Math.max(d.height,d.lineHeight)});
  if(!d.synthetic)n.y=d.y-Math.max(0,d.lineHeight-d.height)/2;
  if(d.height<=d.lineHeight*1.4&&!d.text.includes('\\n'))n.textAutoResize='WIDTH_AND_HEIGHT';
  n.textAlignHorizontal=d.align==='center'?'CENTER':d.align==='right'?'RIGHT':'LEFT';n.fills=color(d.paint);return n;
 }
 if(d.type==='svg'){
  const n=figma.createNodeFromSvg(d.svg);parent.appendChild(n);size(n,d);n.fills=[];
  for(const child of [n,...n.findAll(()=>true)])for(const field of ['fills','strokes']){
   if(!(field in child)||!Array.isArray(child[field]))continue;
   child[field]=child[field].map(p=>{
    if(p.type!=='SOLID')return p;
    const hex='#'+[p.color.r,p.color.g,p.color.b].map(v=>Math.round(v*255).toString(16).padStart(2,'0')).join('');
    const role=d.bindings?.[hex];return role?figma.variables.setBoundVariableForPaint(p,'color',colors.get(role)):p;
   });
  }
  return n;
 }
 const n=rootComponent?figma.createComponent():figma.createFrame();parent.appendChild(n);size(n,d);if(d.slot)slots[d.slot]=n.id;n.fills=color(d.fill);n.clipsContent=!!d.clip;n.opacity=d.opacity??1;radius(n,d.radius);
 const borders=d.borders||[];
 if(borders.some(b=>b.width>0)){
  const b=borders.find(b=>b.width>0);n.strokes=color(b.paint);n.strokeAlign='INSIDE';
  n.strokeTopWeight=borders[0]?.width||0;n.strokeRightWeight=borders[1]?.width||0;n.strokeBottomWeight=borders[2]?.width||0;n.strokeLeftWeight=borders[3]?.width||0;
 }
 for(const c of d.children||[])await build(c,n);
 if(d.component?.family==='Button' && [32,40].includes(Math.round(d.height)))n.setBoundVariable('height',numeric.get(Math.round(d.height)===40?'size/control':'size/compact'));
 if(rootComponent&&d.component?.family==='Button'&&['白垣主题','苍渊主题'].includes(d.component.label)){
  const theme=d.component.label==='白垣主题'?'vallum':'abyssus';
  n.fills=color({role:'theme-'+theme+'-bg'});n.layoutMode='HORIZONTAL';n.primaryAxisSizingMode='AUTO';n.counterAxisSizingMode='FIXED';n.counterAxisAlignItems='CENTER';n.primaryAxisAlignItems='CENTER';const compact=d.component.state==='Selected'?d.width<65:d.width<56;n.itemSpacing=compact?4:6;n.paddingLeft=compact?6:8;n.paddingRight=n.paddingLeft;
  for(const child of n.findAll(()=>true))for(const field of ['fills','strokes'])if(field in child&&Array.isArray(child[field])&&child[field].some(p=>p.type==='SOLID'))child[field]=color({role:'theme-'+theme+'-text'});
  let marker=n.children.find(c=>c.name==='状态标记');if(!marker){marker=figma.createFrame();n.appendChild(marker);marker.name='状态标记';marker.resize(3,3);marker.cornerRadius=1.5;}marker.fills=color({role:'theme-'+theme+'-text'});marker.setBoundVariable('visible',colors.get('theme-'+theme+'-selected'));
 }
 if(rootComponent&&d.component?.family==='Theme'){
  n.layoutMode='HORIZONTAL';n.primaryAxisSizingMode='FIXED';n.counterAxisSizingMode='FIXED';n.counterAxisAlignItems='CENTER';n.itemSpacing=2;n.paddingLeft=3;n.paddingRight=3;n.paddingTop=3;n.paddingBottom=3;
 }
 return n;
}
`;
