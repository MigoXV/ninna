/** Serialize a live view as editable boxes, text and discrete SVGs for Figma.
 * No screenshots or flattened UI images are included in the scene tree.
 */
export function serializePage() {
  const roleNames = [
    "canvas",
    "bg-secondary",
    "surface",
    "surface-subtle",
    "surface-raised",
    "selection",
    "hover",
    "line",
    "button-line",
    "control-line",
    "text",
    "muted",
    "accent",
    "accent-strong",
    "focus",
    "button-primary-bg",
    "button-primary-text",
    "button-primary-hover",
    "chart-primary",
    "chart-secondary",
    "chart-tertiary",
    "chart-fourth",
    "av-success",
    "av-warning",
    "av-danger",
    "av-info",
  ];
  const rootStyle = getComputedStyle(document.documentElement);
  const canvas = document.createElement("canvas").getContext("2d");
  function hex(color) {
    canvas.fillStyle = "#000000";
    canvas.fillStyle = color;
    return canvas.fillStyle;
  }
  const tokens = Object.fromEntries(
    roleNames.map((name) => [
      name,
      hex(rootStyle.getPropertyValue(`--${name}`).trim()),
    ]),
  );
  function paint(color, element, property) {
    if (
      !color ||
      color === "none" ||
      color === "transparent" ||
      color === "rgba(0, 0, 0, 0)"
    )
      return null;
    const value = hex(color);
    if (element.closest?.(".button.primary,.skip-link")) {
      if (property === "background" || property === "border")
        return { role: "button-primary-bg" };
      return { role: "button-primary-text" };
    }
    const priorities =
      property === "text"
        ? [
            "text",
            "muted",
            "accent-strong",
            "av-danger",
            "av-success",
            "accent",
            "button-primary-text",
          ]
        : [
            "canvas",
            "bg-secondary",
            "surface",
            "selection",
            "surface-subtle",
            "line",
            "button-line",
            "muted",
            "accent",
            "av-success",
            "av-danger",
            "text",
            "surface-raised",
          ];
    if (element instanceof SVGElement && value === "#000000")
      return { role: "text" };
    if (element instanceof SVGElement && value === "#ffffff")
      return { role: "surface" };
    const role =
      priorities.find(
        (name) => tokens[name].toLowerCase() === value.toLowerCase(),
      ) ||
      roleNames.find(
        (name) => tokens[name].toLowerCase() === value.toLowerCase(),
      );
    if (!role)
      throw new Error(
        `Unmapped ${property} color ${color} on ${element.tagName}.${element.className}`,
      );
    const alpha = color.match(/rgba\([^)]*,\s*([\d.]+)\s*\)/)?.[1];
    return {
      role,
      ...(alpha && Number(alpha) !== 1 ? { opacity: Number(alpha) } : {}),
    };
  }
  function name(el) {
    return (
      el.getAttribute("aria-label") ||
      el.id ||
      (typeof el.className === "string" ? el.className : "") ||
      el.tagName.toLowerCase()
    ).slice(0, 120);
  }
  function font(style, text) {
    const mono = style.fontFamily.includes("IBM Plex Mono");
    const family = mono
      ? "IBM Plex Mono"
      : /[\u3400-\u9fff]/u.test(text)
        ? "Noto Sans SC"
        : "Inter";
    const weight = Number(style.fontWeight);
    return {
      family,
      style: mono
        ? weight >= 500
          ? "Medium"
          : "Regular"
        : weight >= 650
          ? "Bold"
          : weight >= 550
            ? family === "Noto Sans SC"
              ? "Medium"
              : "Semi Bold"
            : weight >= 450
              ? "Medium"
              : "Regular",
    };
  }
  function textNode(text, rect, origin, style, el, synthetic = false) {
    if (!text.trim() || !rect.width || !rect.height) return null;
    return {
      type: "text",
      name: text.trim().slice(0, 60),
      text,
      x: rect.x - origin.x,
      y: rect.y - origin.y,
      width: rect.width,
      height: rect.height,
      font: font(style, text),
      size: parseFloat(style.fontSize),
      lineHeight:
        parseFloat(style.lineHeight) || parseFloat(style.fontSize) * 1.6,
      letterSpacing: parseFloat(style.letterSpacing) || 0,
      align: style.textAlign,
      paint: paint(style.color, el, "text"),
      synthetic,
    };
  }
  function pseudo(el, which, origin) {
    const s = getComputedStyle(el, which);
    if (
      !s.content ||
      s.content === "none" ||
      s.content === "normal" ||
      s.display === "none"
    )
      return null;
    const width = parseFloat(s.width),
      height = parseFloat(s.height);
    const r = el.getBoundingClientRect();
    // Tiny status markers are the only decorative pseudo-elements we retain.
    if (
      s.content === '""' &&
      width > 0 &&
      height > 0 &&
      width <= 8 &&
      height <= 8
    ) {
      const absolute = s.position === "absolute";
      return {
        type: "box",
        name: "状态标记",
        x: absolute
          ? parseFloat(s.left) || 0
          : r.width - parseFloat(getComputedStyle(el).paddingRight) - width,
        y: absolute ? parseFloat(s.top) || 0 : (r.height - height) / 2,
        width,
        height,
        radius: parseFloat(s.borderRadius) || 0,
        fill: paint(s.backgroundColor, el, "background"),
        children: [],
      };
    }
    return null;
  }
  function visit(
    el,
    origin,
    clip = { left: 0, top: 0, right: innerWidth, bottom: innerHeight },
  ) {
    if (["SCRIPT", "STYLE", "OPTION", "LINK", "NOSCRIPT"].includes(el.tagName))
      return null;
    if (
      el.parentElement?.matches("details:not([open])") &&
      el.tagName !== "SUMMARY"
    )
      return null;
    const s = getComputedStyle(el),
      r = el.getBoundingClientRect();
    if (
      s.display === "none" ||
      s.visibility === "hidden" ||
      Number(s.opacity) === 0 ||
      el.classList.contains("sr-only") ||
      el.classList.contains("skip-link")
    )
      return null;
    if (s.display === "contents" || r.width <= 0 || r.height <= 0) {
      return {
        type: "group",
        children: [...el.children]
          .map((child) => visit(child, origin, clip))
          .filter(Boolean),
      };
    }
    if (
      r.right <= clip.left ||
      r.left >= clip.right ||
      r.bottom <= clip.top ||
      r.top >= clip.bottom
    )
      return null;
    const childClip = {
      left: /(auto|scroll|hidden|clip)/.test(s.overflowX)
        ? Math.max(clip.left, r.left)
        : clip.left,
      right: /(auto|scroll|hidden|clip)/.test(s.overflowX)
        ? Math.min(clip.right, r.right)
        : clip.right,
      top: /(auto|scroll|hidden|clip)/.test(s.overflowY)
        ? Math.max(clip.top, r.top)
        : clip.top,
      bottom: /(auto|scroll|hidden|clip)/.test(s.overflowY)
        ? Math.min(clip.bottom, r.bottom)
        : clip.bottom,
    };
    if (el.tagName.toLowerCase() === "svg") {
      const clone = el.cloneNode(true);
      const originals = [el, ...el.querySelectorAll("*")];
      const copies = [clone, ...clone.querySelectorAll("*")];
      const bindings = {};
      originals.forEach((node, i) => {
        const st = getComputedStyle(node);
        for (const property of ["fill", "stroke"]) {
          if (st[property] && st[property] !== "none") {
            const p = paint(st[property], node, "text");
            copies[i].setAttribute(property, tokens[p.role]);
            bindings[tokens[p.role].toLowerCase()] = p.role;
          }
        }
        copies[i].removeAttribute("class");
        copies[i].setAttribute(
          "font-family",
          st.fontFamily.includes("IBM") ? "IBM Plex Mono" : "Inter",
        );
        copies[i].setAttribute("font-size", st.fontSize);
      });
      clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
      clone.setAttribute("width", String(r.width));
      clone.setAttribute("height", String(r.height));
      return {
        type: "svg",
        name: name(el),
        x: r.x - origin.x,
        y: r.y - origin.y,
        width: r.width,
        height: r.height,
        svg: new XMLSerializer().serializeToString(clone),
        bindings,
      };
    }
    const borders = ["Top", "Right", "Bottom", "Left"].map((side) => ({
      width: parseFloat(s[`border${side}Width`]),
      paint: paint(s[`border${side}Color`], el, "border"),
    }));
    const box = {
      type: "box",
      name: name(el),
      x: r.x - origin.x,
      y: r.y - origin.y,
      width: r.width,
      height: r.height,
      radius: parseFloat(s.borderTopLeftRadius) || 0,
      fill: paint(s.backgroundColor, el, "background"),
      borders,
      opacity: Number(s.opacity),
      clip: /(auto|scroll|hidden|clip)/.test(`${s.overflowX} ${s.overflowY}`),
      children: [],
    };
    if (el.matches('input[type="checkbox"]')) {
      box.fill = { role: el.checked ? "button-primary-bg" : "surface" };
      box.radius = 2;
      box.borders = Array(4).fill({
        width: 1,
        paint: { role: el.checked ? "button-primary-bg" : "muted" },
      });
      if (el.checked)
        box.children.push({
          type: "svg",
          name: "已选中",
          x: 1,
          y: 1,
          width: r.width - 2,
          height: r.height - 2,
          svg: `<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 12 12"><path d="M2 6l2.5 2.5L10 3" fill="none" stroke="${tokens["button-primary-text"]}" stroke-width="1.5"/></svg>`,
          bindings: {
            [tokens["button-primary-text"].toLowerCase()]:
              "button-primary-text",
          },
        });
    } else if (el.matches("input,textarea,select")) {
      const value =
        el.tagName === "SELECT"
          ? el.selectedOptions[0]?.textContent || ""
          : el.value || el.placeholder || "";
      const rect = {
        x: r.x + parseFloat(s.paddingLeft) + 1,
        y: r.y + (r.height - parseFloat(s.fontSize) * 1.6) / 2,
        width:
          r.width - parseFloat(s.paddingLeft) - parseFloat(s.paddingRight) - 2,
        height: parseFloat(s.fontSize) * 1.6,
      };
      const t = textNode(
        el.type === "password" ? "•".repeat(value.length) : value,
        rect,
        r,
        s,
        el,
        true,
      );
      if (t) box.children.push(t);
      if (el.tagName === "SELECT" && s.appearance !== "none")
        box.children.push({
          type: "svg",
          name: "展开选项",
          x: r.width - 22,
          y: (r.height - 12) / 2,
          width: 12,
          height: 12,
          svg: `<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12"><path d="M3 4l3 3 3-3" fill="none" stroke="${tokens.muted}" stroke-width="1.5"/></svg>`,
          bindings: { [tokens.muted.toLowerCase()]: "muted" },
        });
    } else {
      for (const child of el.childNodes) {
        if (child.nodeType === Node.ELEMENT_NODE) {
          const n = visit(child, r, childClip);
          if (n) box.children.push(n);
        }
        if (child.nodeType === Node.TEXT_NODE && child.textContent.trim()) {
          const range = document.createRange();
          range.selectNodeContents(child);
          const value = s.whiteSpace.startsWith("pre")
            ? child.textContent
            : child.textContent.replace(/\s+/g, " ");
          const n = textNode(value, range.getBoundingClientRect(), r, s, el);
          if (n) box.children.push(n);
        }
      }
      for (const which of ["::before", "::after"]) {
        const n = pseudo(el, which, r);
        if (n) box.children.push(n);
      }
    }
    if (el.tagName === "SUMMARY" && s.listStyleType !== "none") {
      const open = el.parentElement.hasAttribute("open");
      box.children.push({
        type: "svg",
        name: open ? "收起说明" : "展开说明",
        x: 0,
        y: (r.height - 8) / 2,
        width: 8,
        height: 8,
        svg: `<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8"><path d="${open ? "M0 2h8L4 6Z" : "M1 0l6 4-6 4Z"}" fill="${tokens.muted}"/></svg>`,
        bindings: { [tokens.muted.toLowerCase()]: "muted" },
      });
    }
    if (el.matches("button,.nav-item,.status,.search-field,.theme-switch")) {
      box.component = {
        family: el.matches(".nav-item")
          ? "Navigation"
          : el.matches(".status")
            ? "Status"
            : el.matches(".search-field")
              ? "Search"
              : el.matches(".theme-switch")
                ? "Theme"
                : "Button",
        label: (el.getAttribute("aria-label") || el.textContent || "操作")
          .replace(/\s+/g, " ")
          .trim()
          .slice(0, 60),
        state:
          el.getAttribute("aria-pressed") === "true" ||
          el.classList.contains("active") ||
          el.classList.contains("selected")
            ? "Selected"
            : el.disabled
              ? "Disabled"
              : "Default",
      };
    }
    return box;
  }
  return {
    capturedAt: new Date().toISOString(),
    width: innerWidth,
    height: innerHeight,
    tokens,
    tree: visit(document.querySelector(".app"), { x: 0, y: 0 }),
  };
}
