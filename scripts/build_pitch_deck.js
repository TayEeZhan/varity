// Builds the final-round pitch deck: submission/SDC2026_HokkienMeeIsPurple_Pitch.pptx
//   node scripts/build_pitch_deck.js <pptx-skill-dir>
// Big type for a business judge: one message per slide, few words, a short source under every outside number.
// Colours and transit grammar from DESIGN.md: white ground, black ink, blue line, stations as white dots with
// black strokes, yellow only for "you are here" and the service-change band.
const path = require("path");
const pptxgen = require("pptxgenjs");
const { applyTheme } = require(path.join(process.argv[2], "scripts", "apply_theme.js"));

const OUT = path.join(__dirname, "..", "submission", "SDC2026_HokkienMeeIsPurple_Pitch.pptx");
const FONT = "Arial"; // DESIGN.md face is Schibsted Grotesk; Arial is its fallback and is on every PC
const HEX = { ink: "121212", ink2: "45464A", ink3: "66676B", paper: "FFFFFF", paper2: "F2F3F1", rule: "D6D7D4",
              blue: "0039A6", green: "00843A", yellow: "FCCC0A", red: "C8102E", orange: "FF6319", grey: "B9BAB7" };
const THEME = {
  name: "Varity Transit", headFontFace: FONT, bodyFontFace: FONT,
  colors: { dk1: HEX.ink, lt1: HEX.paper, dk2: HEX.ink2, lt2: HEX.paper2, accent1: HEX.yellow, accent2: HEX.blue,
            accent3: HEX.green, accent4: HEX.red, accent5: HEX.orange, accent6: HEX.ink3, hlink: HEX.blue, folHlink: HEX.blue },
};

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.33 x 7.5
pres.author = "Hokkien Mee Is Purple";
pres.title = "Varity: prove you are job-ready";
pres.theme = { headFontFace: FONT, bodyFontFace: FONT };
const C = pres.SchemeColor;

pres.defineSlideMaster({
  title: "Dark", background: { color: HEX.ink },
  objects: [{ placeholder: { options: { name: "title", type: "title", x: 0.8, y: 2.3, w: 11.7, h: 1.5, fontSize: 72, bold: true, color: C.background1, valign: "middle", align: "left", margin: 0 }, text: "" } }],
});
pres.defineSlideMaster({
  title: "Content", background: { color: HEX.paper },
  objects: [{ placeholder: { options: { name: "title", type: "title", x: 0.6, y: 0.5, w: 12.1, h: 0.9, fontSize: 40, bold: true, color: C.text1, valign: "top", align: "left", margin: 0 }, text: "" } }],
});

const text = (s, t, o) => s.addText(t, { isTextBox: true, margin: 0, fontFace: FONT, color: C.text1, ...o });
const source = (s, t) => text(s, t, { x: 0.6, y: 6.95, w: 12.1, h: 0.35, fontSize: 12, color: C.text2 });
const box = (s, x, y, w, h, fill, width) => s.addShape(pres.shapes.RECTANGLE, { x, y, w, h, fill: { color: fill }, line: { color: HEX.ink, width: width || 3 } });
const pill = (s, x, y, w, h, fill, lineColor, width) => s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: Math.min(w, h) / 2, fill: { color: fill }, line: { color: lineColor || HEX.ink, width: width || 3 } });
const station = (s, cx, cy, d, fill) => s.addShape(pres.shapes.OVAL, { x: cx - d / 2, y: cy - d / 2, w: d, h: d, fill: { color: fill || HEX.paper }, line: { color: HEX.ink, width: 3 } });
const halo = (s, cx, cy, w, h) => pill(s, cx - w / 2, cy - h / 2, w, h, HEX.yellow, HEX.yellow, 1);
const track = (s, x, y, w) => s.addShape(pres.shapes.LINE, { x, y, w, h: 0, line: { color: HEX.blue, width: 9 } });
const rule = (s, y) => s.addShape(pres.shapes.LINE, { x: 0.6, y, w: 12.1, h: 0, line: { color: HEX.rule, width: 1.5 } });
const arrow = (s, x, y) => s.addShape(pres.shapes.RIGHT_ARROW, { x, y, w: 0.3, h: 0.5, fill: { color: HEX.blue }, line: { color: HEX.blue } });
const terminus = (s, cx, cy) => { halo(s, cx, cy, 1.0, 1.5); pill(s, cx - 0.28, cy - 0.55, 0.56, 1.1, HEX.paper); };
const chartText = () => ({ catAxisLabelFontFace: "+mn-lt", valAxisLabelFontFace: "+mn-lt", dataLabelFontFace: "+mn-lt", legendFontFace: "+mn-lt",
  catAxisLabelColor: HEX.ink, valAxisLabelColor: HEX.ink3, dataLabelColor: HEX.ink, legendColor: HEX.ink });
const quiet = { valAxisHidden: true, valGridLine: { style: "none" }, catGridLine: { style: "none" } };
const content = (title, section) => { const s = pres.addSlide({ masterName: "Content", sectionTitle: section }); s.addText(title, { placeholder: "title" }); return s; };

pres.addSection({ title: "Problem" });
// ── 1. Title ─────────────────────────────────────────────
{
  const s = pres.addSlide({ masterName: "Dark", sectionTitle: "Problem" });
  s.addText("Varity", { placeholder: "title" });
  track(s, 0.8, 1.45, 6.0);
  [1.0, 2.9, 4.8].forEach((x) => station(s, x, 1.45, 0.42));
  terminus(s, 6.8, 1.45);
  text(s, "Don't just learn it. Prove it.", { x: 0.8, y: 3.85, w: 11.7, h: 0.9, fontSize: 40, bold: true, color: C.background1 });
  text(s, "Hokkien Mee Is Purple · Tay Ee Zhan, Goh Sheng Kuan · SDC Hackathon 2026, Domain 1", { x: 0.8, y: 6.3, w: 11.7, h: 0.5, fontSize: 18, color: C.background1 });
  s.addNotes("Hi, we are Hokkien Mee Is Purple, and this is Varity. One line: don't just learn it, prove it.");
}

// ── 2. The fear: skills expire ──────────────────────────
{
  const s = content("Will what I learn today still matter?", "Problem");
  text(s, "70%", { x: 0.6, y: 1.6, w: 6.0, h: 2.4, fontSize: 170, bold: true, color: C.accent4 });
  text(s, "of the skills in most jobs will change by 2030.", { x: 6.9, y: 2.2, w: 5.8, h: 1.6, fontSize: 36, bold: true });
  // service-change band (DESIGN.md): full-width yellow field with a black plate
  s.addShape(pres.shapes.RECTANGLE, { x: 0, y: 4.7, w: 13.333, h: 1.4, fill: { color: HEX.yellow }, line: { color: HEX.yellow, width: 0 } });
  s.addShape(pres.shapes.RECTANGLE, { x: 0.6, y: 5.12, w: 2.9, h: 0.56, fill: { color: HEX.ink }, line: { color: HEX.ink, width: 0 } });
  text(s, "Service change", { x: 0.6, y: 5.12, w: 2.9, h: 0.56, fontSize: 22, bold: true, color: C.background1, align: "center", valign: "middle" });
  text(s, "In tech, the skill you learn now may be old next year.", { x: 3.8, y: 4.95, w: 8.9, h: 0.9, fontSize: 28, bold: true, valign: "middle" });
  source(s, "Source: LinkedIn Work Change Report (Jan 2025)");
  s.addNotes("LinkedIn expects 70 percent of the skills in most jobs to change by 2030. Ten years ago, a programmer learned a few languages, built a few projects, and was ready. Now the target moves every few months.");
}

// ── 3. Our data: the list keeps moving ──────────────────
{
  const s = content("The skills employers want keep changing", "Problem");
  text(s, "Tech job posts that ask for the skill", { x: 0.6, y: 1.55, w: 6.0, h: 0.5, fontSize: 20, bold: true, color: C.text2 });
  text(s, "2019", { x: 6.2, y: 1.55, w: 1.8, h: 0.5, fontSize: 22, bold: true, align: "center", color: C.text2 });
  text(s, "2026", { x: 8.4, y: 1.55, w: 1.8, h: 0.5, fontSize: 22, bold: true, align: "center", color: C.text2 });
  const rows = [["LLM / GenAI", "0%", "15%", true], ["TypeScript", "10%", "24%", true], ["Java", "11%", "4%", false], ["Ruby", "10%", "3%", false]];
  rows.forEach(([skill, a, b, up], i) => {
    const y = 2.15 + i * 0.95;
    rule(s, y);
    text(s, skill, { x: 0.6, y: y + 0.1, w: 5.4, h: 0.75, fontSize: 34, bold: true, valign: "middle" });
    text(s, a, { x: 6.2, y: y + 0.1, w: 1.8, h: 0.75, fontSize: 34, align: "center", valign: "middle", color: C.text2 });
    text(s, "→", { x: 7.9, y: y + 0.1, w: 0.6, h: 0.75, fontSize: 30, align: "center", valign: "middle", color: C.text2 });
    text(s, b, { x: 8.4, y: y + 0.1, w: 1.8, h: 0.75, fontSize: 40, bold: true, align: "center", valign: "middle", color: up ? C.accent3 : C.accent4 });
    text(s, up ? "▲ Rising" : "▼ Falling", { x: 10.5, y: y + 0.1, w: 2.2, h: 0.75, fontSize: 28, bold: true, valign: "middle", color: up ? C.accent3 : C.accent4 });
  });
  rule(s, 5.95);
  text(s, "Java still works. Far fewer new jobs ask for it.", { x: 0.6, y: 6.1, w: 12.1, h: 0.7, fontSize: 30, bold: true });
  source(s, "Source: Varity analysis of 48,491 Hacker News \"Who is hiring\" posts (share of posts naming the skill, 2019 vs 2026)");
  s.addNotes("We see it in our own data: 48 thousand Hacker News hiring posts since 2019. In 2019 no post asked for LLM skills; now 15 percent do. In 2019, 11 percent of posts asked for Java; now only 4 percent do. Java still works, but far fewer new jobs ask for it. A safe skill in 2019 is a rare ask today.");
}

// ── 4. Anthropic: AI hits computer work first ───────────
{
  const s = content("AI hits computer work first", "Problem");
  const labels = ["Computer & maths", "Office & admin", "Business & finance", "Legal", "Engineering"];
  s.addChart(pres.charts.BAR, [
    { name: "AI could do", labels, values: [94, 90, 75, 68, 65] },
    { name: "AI already does", labels, values: [33, 25, 22, 15, 14] },
  ], {
    x: 0.6, y: 1.6, w: 7.9, h: 5.1, barDir: "bar", barGrouping: "clustered", chartColors: [HEX.grey, HEX.red],
    showValue: true, dataLabelPosition: "outEnd", dataLabelFontSize: 16, dataLabelFormatCode: "0\"%\"", dataLabelFontBold: true,
    catAxisLabelFontSize: 16, catAxisOrientation: "maxMin", valAxisMaxVal: 110, showLegend: true, legendPos: "t", legendFontSize: 18,
    barGapWidthPct: 40, ...quiet, ...chartText(),
  });
  text(s, "33%", { x: 8.9, y: 1.8, w: 3.85, h: 1.2, fontSize: 80, bold: true, color: C.accent4 });
  text(s, "of computer work is already done with AI. The most of any field.", { x: 8.9, y: 3.05, w: 3.85, h: 1.3, fontSize: 22, bold: true });
  text(s, "75%", { x: 8.9, y: 4.45, w: 3.85, h: 1.2, fontSize: 80, bold: true, color: C.accent4 });
  text(s, "for computer programmers. No job is higher.", { x: 8.9, y: 5.7, w: 3.85, h: 0.9, fontSize: 22, bold: true });
  source(s, "Source: Anthropic, Labor market impacts of AI (5 Mar 2026): theoretical vs observed AI coverage of tasks");
  s.addNotes("Anthropic, the company behind Claude, studied every type of job. Grey is how much of the work AI could do in theory. Red is how much people already do with AI today. Computer and maths work is on top: AI could do 94 percent, and 33 percent is already done with AI, more than any other field. For computer programmers it is 75 percent. Tech workers feel AI first.");
}

// ── 5. Tech graduates feel it first ────────────────
{
  const s = content("Tech graduates feel it first", "Problem");
  const stats = [["7%", "of new computer science graduates have no job."], ["−20%", "young software developers in work since 2022."], ["38%", "of tech leaders cut junior hiring."]];
  stats.forEach(([big, small], i) => {
    const x = 0.6 + i * 4.1;
    text(s, big, { x, y: 1.9, w: 3.9, h: 1.6, fontSize: 96, bold: true, color: C.accent4 });
    text(s, small, { x, y: 3.8, w: 3.6, h: 1.5, fontSize: 28, bold: true });
  });
  source(s, "Sources (US): NY Fed, recent graduates by major (Feb 2026); Stanford Digital Economy Lab (Aug 2025); CodePath survey (Fortune, Dec 2025)");
  s.addNotes("And the people who feel it first are tech graduates. In the US, 7 percent of new computer science graduates have no job; computer engineering is 7.8, among the highest of all majors. Stanford found about 20 percent fewer young software developers in work than in late 2022. 38 percent of engineering leaders cut junior hiring. Malaysia does not publish jobless rates by field, so these are US numbers.");
}

// ── 6. Who we help ──────────────────────────────────────
{
  const s = content("Who we help", "Problem");
  const who = [["Fresh CS graduates", "Looking for a first job"], ["Developers fearing layoffs", "Keeping their skills current"], ["People switching into tech", "Finding the right first role"]];
  who.forEach(([t, sub], i) => {
    const y = 1.8 + i * 1.45;
    pill(s, 0.6, y, 6.2, 1.0, HEX.paper);
    text(s, t, { x: 0.95, y, w: 5.7, h: 1.0, fontSize: 30, bold: true, valign: "middle" });
    text(s, sub, { x: 7.2, y, w: 5.5, h: 1.0, fontSize: 28, valign: "middle", color: C.text2 });
  });
  text(s, "One shared fear: will my skills still count?", { x: 0.6, y: 6.15, w: 12.1, h: 0.7, fontSize: 32, bold: true, color: C.accent2 });
  s.addNotes("We built Varity for people in tech who share one fear. Fresh CS graduates looking for a first job. Developers afraid of the next layoff. And people switching into tech. They all ask the same question: will my skills still count?");
}

pres.addSection({ title: "Solution" });
// ── 7. Solution: four stops ─────────────────────────────
{
  const s = content("Varity: from CV to proof in four stops", "Solution");
  const stops = [["Read your CV", "Skills, with proof"], ["Match a role", "Your match % and demand"], ["Learn", "A free daily plan"], ["Prove it", "A project, reviewed by AI"]];
  track(s, 2.15, 2.7, 9.0);
  stops.forEach(([head, sub], i) => {
    const cx = 2.15 + i * 3.0;
    if (i === 3) terminus(s, cx, 2.7); else station(s, cx, 2.7, 0.6);
    text(s, head, { x: cx - 1.45, y: 3.7, w: 2.9, h: 0.6, fontSize: 30, bold: true, align: "center" });
    text(s, sub, { x: cx - 1.4, y: 4.4, w: 2.8, h: 1.1, fontSize: 24, align: "center", color: C.text2 });
  });
  text(s, "Stop 4 is what no one else does.", { x: 0.6, y: 5.95, w: 12.1, h: 0.7, fontSize: 32, bold: true, color: C.accent2, align: "center" });
  s.addNotes("Varity takes you from your CV to proof in four stops. One: it reads your CV, and every skill must quote the sentence that proves it. Two: it ranks 8 tech roles by 70 percent skill match and 30 percent job demand, and shows the gap. Three: it turns the gap into a free daily plan. Four, the one no one else does: you build a project for that role, and Varity reviews your GitHub. The live demo shows all four.");
}

// ── 8. Employers want proof ──────────────────────────────
{
  const s = content("Employers want proof, not certificates", "Solution");
  const labels = ["Side projects", "Internships", "GitHub code", "Degree", "School name", "Certificates"];
  s.addChart(pres.charts.BAR, [{ name: "Leaders who value it", labels, values: [38, 35, 34, 23, 17, 4] }], {
    x: 0.6, y: 1.6, w: 7.9, h: 5.1, barDir: "bar", chartColors: [HEX.green, HEX.green, HEX.green, HEX.ink3, HEX.ink3, HEX.red],
    invertedColors: [HEX.green, HEX.green, HEX.green, HEX.ink3, HEX.ink3, HEX.red],
    showValue: true, dataLabelPosition: "outEnd", dataLabelFontSize: 22, dataLabelFormatCode: "0\"%\"", dataLabelFontBold: true,
    catAxisLabelFontSize: 20, catAxisOrientation: "maxMin", valAxisMaxVal: 44, showLegend: false, barGapWidthPct: 35, ...quiet, ...chartText(),
  });
  text(s, "Projects beat degrees.", { x: 8.9, y: 2.2, w: 3.85, h: 1.4, fontSize: 40, bold: true, color: C.accent3 });
  text(s, "Certificates come last.", { x: 8.9, y: 4.0, w: 3.85, h: 1.4, fontSize: 40, bold: true, color: C.accent4 });
  source(s, "Source: CodePath survey of 200+ engineering leaders (Fortune, 18 Dec 2025)");
  s.addNotes("So how do you show you are ready? Engineering leaders trust side projects, internships and GitHub code. Degrees come after. Course certificates come last, at 4 percent. Finishing ten online courses proves almost nothing to an employer.");
}

pres.addSection({ title: "Why us" });
// ── 9. What sets us apart ──────────────────────────────
{
  const s = content("What sets us apart", "Why us");
  const pts = [["Proof, not certificates", "A project for your target role marks the skill Applied."],
               ["A jury of 3 AIs marks your project", "Claude, GPT and DeepSeek. 2 of 3 must agree."],
               ["Every skill shows its proof", "A quote from your CV or your code. AI never makes up a number."],
               ["Live demand from real job posts", "Refreshed every day and tested on past years."]];
  pts.forEach(([head, sub], i) => {
    const y = 1.6 + i * 1.3;
    if (i === 0) halo(s, 1.0, y + 0.4, 0.95, 0.95);
    station(s, 1.0, y + 0.4, 0.6, i === 0 ? HEX.ink : HEX.paper);
    text(s, head, { x: 1.7, y, w: 11.0, h: 0.65, fontSize: 32, bold: true });
    text(s, sub, { x: 1.7, y: y + 0.65, w: 11.0, h: 0.5, fontSize: 22, color: C.text2 });
  });
  s.addNotes("What sets us apart. First, and most important: proof, not certificates. You build a project for your target role, and the skill is marked Applied. Second: a jury of three AI models from three companies, Claude, GPT and DeepSeek, reviews and marks your project; two of three must agree, so no single AI decides. Third: every skill shows its proof, a quote from your CV or your code, and AI never makes up a number. Fourth: demand comes from real job posts, refreshed every day and tested on past years.");
}

// ── 10. Prove it with a project ────────────────────────
{
  const s = content("Prove it with a project", "Why us");
  const flow = [["Learned", "Course done"], ["Build", "A project for your target role"], ["Review", "3 AIs review and mark it"], ["Applied", "The skill counts in full"]];
  flow.forEach(([head, sub], i) => {
    const x = 0.6 + i * 3.15;
    box(s, x, 1.7, 2.8, 2.5, i === 3 ? HEX.yellow : HEX.paper);
    text(s, head, { x: x + 0.2, y: 1.95, w: 2.4, h: 0.7, fontSize: 32, bold: true, align: "center" });
    text(s, sub, { x: x + 0.2, y: 2.8, w: 2.4, h: 1.2, fontSize: 22, align: "center" });
    if (i < 3) arrow(s, x + 2.83, 2.7);
  });
  text(s, "½", { x: 0.6, y: 4.6, w: 1.4, h: 1.5, fontSize: 96, bold: true, color: C.text2 });
  text(s, "Studied only: counts half.", { x: 2.1, y: 4.95, w: 4.5, h: 0.9, fontSize: 30, bold: true });
  text(s, "×1", { x: 6.9, y: 4.6, w: 1.6, h: 1.5, fontSize: 96, bold: true, color: C.accent3 });
  text(s, "Project passed: counts in full.", { x: 8.6, y: 4.95, w: 4.2, h: 0.9, fontSize: 30, bold: true });
  s.addNotes("This is our edge. Finishing a course only counts half. To make a skill count in full, you build a project made for your target role and submit your GitHub link. Code checks run first, then three AI models from three companies review and mark it, and every mark must point to a real line in your code. Pass, and the skill is stamped Applied, with a link an employer can open.");
}

// ── 11. CV builder and assistant ───────────────────────
{
  const s = content("Then: a CV built from your proof", "Why us");
  const tools = [["CV builder", "Writes your CV for the role you want, from your proven skills."],
                 ["CV assistant", "Chat with it to tailor your CV to a job ad. It asks before it adds anything."]];
  tools.forEach(([head, sub], i) => {
    const x = 0.6 + i * 6.2;
    box(s, x, 1.7, 5.9, 2.9, i === 1 ? HEX.paper2 : HEX.paper);
    text(s, head, { x: x + 0.4, y: 1.95, w: 5.1, h: 0.8, fontSize: 36, bold: true, color: C.accent2 });
    text(s, sub, { x: x + 0.4, y: 2.85, w: 5.1, h: 1.5, fontSize: 26 });
  });
  text(s, "Nothing invented.", { x: 0.6, y: 5.0, w: 12.1, h: 0.75, fontSize: 36, bold: true });
  text(s, "Every line must come from your CV, your proof or your own words.", { x: 0.6, y: 5.75, w: 12.1, h: 0.7, fontSize: 28, color: C.text2 });
  s.addNotes("Once a skill is proven, Varity helps you show it. The CV builder writes a CV for your target role from your proven skills. The CV assistant is a chat: paste a job ad and it tailors your CV, one checked edit at a time, and it asks you before adding anything new. Code rejects any claim your CV, your proof or your own answers cannot back, and any stronger verb than you used.");
}

// ── 12. Competitive table ───────────────────────────────
{
  const s = content("What only Varity does", "Why us");
  const cols = ["Jobscan", "JobStreet", "roadmap.sh", "Coursera", "LinkedIn", "Varity"];
  const Y = "✓", P = "~", N = "";
  const rows = [
    ["Reads your CV", Y, P, N, N, Y, Y],
    ["Match % to a role", Y, N, N, N, Y, Y],
    ["Learning plan", N, N, Y, Y, Y, Y],
    ["Each skill shows its proof", N, N, N, N, N, Y],
    ["Project from your skill gap", N, N, P, P, N, Y],
    ["AI review of your GitHub", N, N, N, N, N, Y],
  ];
  const head = [{ text: "", options: { fill: { color: HEX.paper } } }, ...cols.map((c, i) => ({ text: c,
    options: { bold: true, fontSize: 17, align: "center", color: HEX.ink, fill: { color: i === 5 ? HEX.yellow : HEX.paper2 } } }))];
  const body = rows.map((r, ri) => r.map((v, ci) => ci === 0
    ? { text: v, options: { fontSize: 20, bold: ri >= 3, color: HEX.ink } }
    : { text: v, options: { fontSize: 28, bold: true, align: "center", color: v === Y ? (ci === 6 ? HEX.ink : HEX.green) : HEX.ink3,
        fill: { color: ci === 6 ? "FFF2B3" : HEX.paper } } }));
  s.addTable([head, ...body], { x: 0.6, y: 1.6, w: 12.1, colW: [4.05, 1.25, 1.45, 1.55, 1.3, 1.25, 1.25], rowH: 0.7,
    border: { type: "solid", pt: 1, color: HEX.rule }, fontFace: FONT, valign: "middle" });
  text(s, "✓ yes    ~ partly", { x: 0.6, y: 6.75, w: 6, h: 0.4, fontSize: 16, color: C.text2 });
  s.addNotes("Others cover parts of the journey. Jobscan and LinkedIn read your CV and give a match. roadmap.sh, Coursera and LinkedIn Learning give a learning plan. What only Varity does: every skill shows the sentence from your CV that proves it, the project is built from your own skill gap for your target role, and three AI models review your own GitHub code. Coursera's Guided Projects and roadmap.sh's project ideas are general, not built from your gap, so they are marked partly.");
}

pres.addSection({ title: "Demo" });
// ── 11. Demo divider ────────────────────────────────────
{
  const s = pres.addSlide({ masterName: "Dark", sectionTitle: "Demo" });
  s.addText("Live demo", { placeholder: "title" });
  text(s, "Aina, a sample junior developer, from CV to a proven skill.", { x: 0.8, y: 3.85, w: 11.7, h: 1.2, fontSize: 34, color: C.background1 });
  text(s, "verity--eezhan0805.replit.app", { x: 0.8, y: 6.3, w: 11.7, h: 0.5, fontSize: 20, color: C.background1 });
  s.addNotes("Switch to the app. 5 minutes. Aina is synthetic: say so. CV upload, Why NN%, Pathway, then spend the most time on Project and Cert stations and the sample review. End on the APPLIED stamp.");
}

pres.addSection({ title: "Technology" });
// ── 12. Tech: how it works ──────────────────────────────
{
  const s = content("How it works: facts from code, AI only points", "Technology");
  const st = [["Job posts", false], ["Role labels", true], ["Forecast", false], ["Your CV", true], ["Match, plan", false], ["Project review", true]];
  const x0 = 1.3, gap = 10.73 / 5;
  track(s, x0, 2.3, 10.73);
  st.forEach(([head, ai], i) => {
    const cx = x0 + i * gap;
    station(s, cx, 2.3, 0.6, ai ? HEX.paper : HEX.ink);
    text(s, head, { x: cx - 1.05, y: 2.85, w: 2.1, h: 0.6, fontSize: 22, bold: true, align: "center" });
  });
  station(s, 1.0, 4.05, 0.45, HEX.ink);
  text(s, "Code only", { x: 1.45, y: 3.8, w: 4.0, h: 0.5, fontSize: 26, bold: true });
  station(s, 6.0, 4.05, 0.45, HEX.paper);
  text(s, "AI points, code checks", { x: 6.45, y: 3.8, w: 6.2, h: 0.5, fontSize: 26, bold: true });
  rule(s, 4.75);
  const facts = [["48,491", "real job posts, daily"], ["94%", "of results inside our forecast range"], ["0", "numbers made up by AI"]];
  facts.forEach(([big, small], i) => {
    const x = 0.6 + i * 4.1;
    text(s, big, { x, y: 4.95, w: 3.8, h: 1.0, fontSize: 54, bold: true, color: C.accent2 });
    text(s, small, { x, y: 5.95, w: 3.8, h: 0.8, fontSize: 20, bold: true });
  });
  source(s, "Forecast range: rolling backtest Nov 2023 to Oct 2025, 40 skills (data/backtest.json). Python FastAPI on Replit; data refreshes daily.");
  s.addNotes("End to end: job posts come in every day. DeepSeek names the role in each post, and code keeps the label only if the quote is in the post. The forecast is the simplest model that won our backtest; 94 percent of real results landed inside its 80 percent range. Claude Haiku reads your CV, and code checks every quote. Matching and planning are pure code. AI never makes up a number. Labelling all 48 thousand posts cost US$2.63 once.");
}

// ── 13. Tech: AI trend signals, checked by a jury ──────
{
  const s = content("AI trend signals, checked by a jury", "Technology");
  const flow = [["AI news", "Official, research and community sources"], ["Ranked", "Code scores each story; Jev gives a second opinion"],
                ["3-model jury", "Claude Sonnet, GPT Sol and Gemini Argon label the same stories"], ["Fixed", "The blind spots the jury found"]];
  flow.forEach(([head, sub], i) => {
    const x = 0.6 + i * 3.15;
    box(s, x, 1.7, 2.8, 2.7, i === 3 ? HEX.yellow : HEX.paper);
    text(s, head, { x: x + 0.2, y: 1.95, w: 2.4, h: 0.7, fontSize: 28, bold: true, align: "center" });
    text(s, sub, { x: x + 0.2, y: 2.75, w: 2.4, h: 1.5, fontSize: 20, align: "center" });
    if (i < 3) arrow(s, x + 2.83, 2.8);
  });
  text(s, "0.37 → 0.53", { x: 0.6, y: 4.75, w: 6.0, h: 1.2, fontSize: 72, bold: true, color: C.accent3 });
  text(s, "ranking quality after the jury's fixes.", { x: 6.9, y: 4.95, w: 5.8, h: 1.2, fontSize: 26, bold: true });
  source(s, "Ranking quality: NDCG@10 against the jury's labels (backend/signals/eval/jury.py; docs/how-varity-works.md)");
  s.addNotes("Varity also tracks AI news, so users see what is changing. Code scores each story; Jev, a decision model from TypeSafe AI, gives a second opinion. To check the ranking without bias, three models from three companies, Claude Sonnet, GPT Sol and Gemini Argon, label the same stories on their own; the ranked models are never on the jury. The jury showed that urgent security news was buried. We fixed the story grouping and added a security rule, and ranking quality rose from 0.37 to 0.53. Note: the jury grades the ranker, it does not train a model.");
}

// ── 14. Tech: how a project is reviewed ─────────────────
{
  const s = content("How a project is reviewed", "Technology");
  const steps = [["Code checks", "Real repo, tests pass, demo live"], ["3 AI jurors", "Claude, GPT and DeepSeek vote"],
                 ["Cite check", "Each vote must quote real code"], ["Verdict", "2 of 3 agree: Applied"]];
  steps.forEach(([head, sub], i) => {
    const x = 0.6 + i * 3.15;
    box(s, x, 1.7, 2.8, 2.7, i === 3 ? HEX.yellow : HEX.paper);
    text(s, head, { x: x + 0.2, y: 1.95, w: 2.4, h: 0.7, fontSize: 28, bold: true, align: "center" });
    text(s, sub, { x: x + 0.2, y: 2.8, w: 2.4, h: 1.4, fontSize: 22, align: "center" });
    if (i < 3) arrow(s, x + 2.83, 2.8);
  });
  text(s, "No single AI can pass you.", { x: 0.6, y: 4.9, w: 12.1, h: 0.75, fontSize: 36, bold: true });
  text(s, "And none can invent evidence.", { x: 0.6, y: 5.65, w: 12.1, h: 0.75, fontSize: 36, bold: true, color: C.accent2 });
  s.addNotes("Step one is pure code: a real repo, not a fork, commits over several days, tests passing, a live demo. Step two, three AI models from three companies, Claude, GPT-5.4 mini and DeepSeek V4, vote on each skill. Step three, a vote only counts if the code it quotes is really on the line it cites. Two of three must agree, otherwise the review is delayed, never a free pass.");
}

pres.addSection({ title: "Business" });
// ── 14. Business model ──────────────────────────────────
{
  const s = content("How we make money", "Business");
  const cards = [["B2C", "Students", "RM32", "a month (US$8)"], ["B2B", "Universities", "Licence", "a year, per class"], ["B2B", "Employers", "Fee", "per hire of a proven graduate"]];
  cards.forEach(([tag, who, price, per], i) => {
    const x = 0.6 + i * 4.1, dark = i === 2;
    box(s, x, 1.7, 3.8, 4.4, dark ? HEX.ink : (i === 1 ? HEX.paper2 : HEX.paper), 2);
    pill(s, x + 0.3, 1.95, 1.1, 0.5, dark ? HEX.paper : HEX.ink, dark ? HEX.paper : HEX.ink, 1);
    text(s, tag, { x: x + 0.3, y: 1.95, w: 1.1, h: 0.5, fontSize: 18, bold: true, align: "center", valign: "middle", color: dark ? C.text1 : C.background1 });
    text(s, who, { x: x + 0.3, y: 2.7, w: 3.2, h: 0.7, fontSize: 30, bold: true, color: dark ? C.background1 : C.text1 });
    text(s, price, { x: x + 0.3, y: 3.5, w: 3.2, h: 1.2, fontSize: 60, bold: true, color: dark ? C.background1 : C.accent2 });
    text(s, per, { x: x + 0.3, y: 4.6, w: 3.2, h: 0.9, fontSize: 24, color: dark ? C.background1 : C.text1 });
    if (i === 0) text(s, "Covers our AI costs", { x: x + 0.3, y: 5.2, w: 3.2, h: 0.5, fontSize: 20, bold: true, color: C.accent2 });
  });
  text(s, "Universities and employers also get the Applied label: proof they can trust.", { x: 0.6, y: 6.3, w: 12.1, h: 0.6, fontSize: 24, bold: true });
  source(s, "RM32 at RM4.06 per US$1 (XE mid-market rate, 30 Oct 2026)");
  s.addNotes("Students pay about 32 ringgit a month, which is 8 US dollars. That covers the AI that reads CVs and reviews projects. Universities pay a yearly licence per class, to see which students have proven which skills. Employers pay a fee per hire of a graduate with Applied projects. The Applied label is what both universities and employers pay to trust.");
}

// ── 15. Scaling ─────────────────────────────────────────
{
  const s = content("How we grow", "Business");
  const steps = [["Now", "Tech roles in Malaysia"], ["Next", "More universities and employers"], ["Then", "More languages, worldwide"], ["Later", "Every field, with AI"]];
  track(s, 2.1, 2.6, 9.1);
  steps.forEach(([when, what], i) => {
    const cx = 2.1 + i * (9.1 / 3);
    if (i === 0) { halo(s, cx, 2.6, 1.0, 1.0); station(s, cx, 2.6, 0.6, HEX.ink); }
    else if (i === 3) pill(s, cx - 0.28, 2.05, 0.56, 1.1, HEX.paper);
    else station(s, cx, 2.6, 0.6);
    text(s, when, { x: cx - 1.5, y: 3.5, w: 3.0, h: 0.7, fontSize: 34, bold: true, align: "center", color: i === 0 ? C.text1 : C.accent2 });
    text(s, what, { x: cx - 1.45, y: 4.25, w: 2.9, h: 1.2, fontSize: 26, align: "center" });
  });
  text(s, "Same engine, new data: any field can follow.", { x: 0.6, y: 5.9, w: 12.1, h: 0.7, fontSize: 30, bold: true });
  s.addNotes("Today we cover tech roles in Malaysia. Next, we sell to more students and sign more universities and employers. Then we add more languages and market Varity worldwide. Later, we use the same AI engine for every field, not only computer science. A new field only needs job data and a skill list.");
}

pres.addSection({ title: "Close" });
// ── 16. Close ───────────────────────────────────────────
{
  const s = pres.addSlide({ masterName: "Dark", sectionTitle: "Close" });
  s.addText("Don't just learn it.", { placeholder: "title" });
  text(s, "Prove it.", { x: 0.8, y: 3.75, w: 11.7, h: 1.2, fontSize: 72, bold: true, color: C.background1 });
  track(s, 0.8, 1.45, 6.0);
  [1.0, 2.9, 4.8].forEach((x) => station(s, x, 1.45, 0.42));
  terminus(s, 6.8, 1.45);
  text(s, "verity--eezhan0805.replit.app", { x: 0.8, y: 6.1, w: 11.7, h: 0.6, fontSize: 24, color: C.background1 });
  s.addNotes("Varity: don't just learn it, prove it. It supports SDG 4.4, skills for work, and SDG 8.5, decent work for young people. Code: github.com/TayEeZhan/varity. Thank you, we are happy to take questions.");
}

(async () => {
  await pres.writeFile({ fileName: OUT });
  await applyTheme(OUT, THEME);
  console.log("written", OUT);
})();
