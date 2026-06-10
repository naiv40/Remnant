/*
╔══════════════════════════════════════════════════════════════════════════════╗
║  REMNANT — HUD                                                               ║
║  Launch AFTER remnant_sc.scd and remnant_conv.scd                            ║
║                                                                              ║
║  Block 1 — gate synth + score loader + timer engine                         ║
║  Block 2 — HUD window                                                        ║
╚══════════════════════════════════════════════════════════════════════════════╝
*/


// ═══════════════════════════════════════════════════════════════════════════
// BLOCK 1 — Gate + Score + Timer
// ═══════════════════════════════════════════════════════════════════════════
(
if(~r_mixBus.isNil) { Error("Launch remnant_sc.scd first").throw };

// ── Gate ─────────────────────────────────────────────────────────────────────
SynthDef(\r_gate, {
	|inBus=0, outBus=0, thresh= -42, attackTime=0.08, releaseTime=1.2, depth=1.0|
	var sig  = Mix.ar(SoundIn.ar([0,1,2,3])) / 4.0;
	var amp  = Amplitude.ar(sig, attackTime, releaseTime);
	var gate = (amp > thresh.dbamp).lag(attackTime, releaseTime);
	var env  = ((1 - depth) + (gate * depth)).clip(0, 1);
	Out.kr(outBus, env);
}).add;

~r_gateBus     = Bus.control(s, 1);
~r_gateThresh  = -42.0;
~r_gateAttack  =  0.08;
~r_gateRelease =  1.2;
~r_gateDepth   =  1.0;

~r_gateSynth = Synth(\r_gate, [
	\inBus,       ~r_mixBus.index,
	\outBus,      ~r_gateBus.index,
	\thresh,      ~r_gateThresh,
	\attackTime,  ~r_gateAttack,
	\releaseTime, ~r_gateRelease,
	\depth,       ~r_gateDepth,
], target: ~r_gProc, addAction: \addToHead);

~r_hudGateLevel = 1.0;
~r_flucoUpdateOrig = ~r_flucoUpdate;
~r_flucoUpdate = { |flucoTension|
	var gv;
	gv = ~r_hudGateLevel ? 1.0;
	~r_flucoUpdateOrig.(flucoTension * gv);
};

// ── Score: costruisce la sequenza dei gesti ───────────────────────────────────
// Legge ~r_score (già caricato da remnant_sc.scd).
// Ogni gesto: (index, tStart, tEnd, cat, tension, azimuth medio degli eventi).
~r_hudGestures = [];
~r_hudDuration = 0.0;
~r_hudManualTension = nil;

if(~r_score.notNil) {
	var gest = ~r_score["gestures"];
	~r_hudDuration = ~r_score["duration"].asFloat;
	~r_hudGestures = gest.collect { |g|
		var evs = g["events"] ?? [];
		var az  = if(evs.size > 0) {
			evs.collect { |e| e["azimuth"].asFloat }.sum / evs.size
		} { 180.0 };
		var cat     = g["lachenmann"] ?? (g["dynamic_form"] ?? "Neutro");
		var tension = g["tension"].asFloat;
		(
			index:   g["index"].asInteger,
			tStart:  g["t_start"].asFloat,
			tEnd:    g["t_end"].asFloat,
			cat:     cat,
			tension: tension,
			azimuth: az.round(0.1),
		)
	};
	("Score: " ++ ~r_hudGestures.size ++ " gesti · "
	 ++ ~r_hudDuration ++ "s totali").postln;
} {
	"HUD: nessuna score caricata — avvia remnant_sc.scd".postln;
};

// ── Timer state ───────────────────────────────────────────────────────────────
~r_timerRunning   = false;
~r_timerStartTime = 0.0;
~r_timerGestIdx   = 0;
~r_timerRoutine   = nil;
~r_vizEventIdx    = 0;   // indice evento corrente per la visualizzazione p5.js

// Avanza al gesto idx e chiama ~r_gesture globalmente
~r_hudAdvanceGesture = { |idx|
	var g, tension;
	g = ~r_hudGestures[idx];
	if(g.notNil) {
		tension = ~r_hudManualTension ?? g[\tension];
		~r_timerGestIdx = idx;
		AppClock.sched(0, {
			~r_gesture.(g[\cat], tension, g[\azimuth]);
			if(~r_hudUpdateDisplay.notNil) { ~r_hudUpdateDisplay.() };
			nil;
		});
		("▶ Gesto " ++ (idx+1) ++ "/" ++ ~r_hudGestures.size
		 ++ "  " ++ g[\cat]
		 ++ "  t=" ++ tension.round(0.01)
		 ++ "  az=" ++ g[\azimuth]).postln;
	};
};

// START: lancia Routine su SystemClock che scorre i gesti secondo la score
~r_hudStart = {
	if(~r_timerRunning.not and: { ~r_hudGestures.size > 0 }) {
		~r_timerRunning   = true;
		~r_timerGestIdx   = 0;
		~r_timerStartTime = thisThread.seconds;

		~r_timerRoutine = Routine({
			~r_hudGestures.size.do { |i|
				var g, gestDur;
				g       = ~r_hudGestures[i];
				gestDur = g[\tEnd] - g[\tStart];
				~r_hudAdvanceGesture.(i);
				gestDur.wait;
			};
			~r_timerRunning = false;
			AppClock.sched(0, {
				if(~r_hudUpdateDisplay.notNil) { ~r_hudUpdateDisplay.() };
				nil;
			});
			"═══ REMNANT fine ═══".postln;
		}).play(SystemClock);

		"═══ REMNANT start ═══".postln;
	} {
		if(~r_timerRunning) {
			"Timer già in esecuzione.".postln
		} {
			"Nessuna score caricata.".postln
		};
	};
};

// STOP: interrompe la Routine e azzera lo stato
~r_hudStop = {
	if(~r_timerRoutine.notNil) { ~r_timerRoutine.stop };
	~r_timerRunning = false;
	~r_timerGestIdx = 0;
	AppClock.sched(0, {
		if(~r_hudUpdateDisplay.notNil) { ~r_hudUpdateDisplay.() };
		nil;
	});
	"═══ REMNANT stop ═══".postln;
};

// ── Stereo fold for headphones ────────────────────────────────────────────────────
SynthDef(\r_stereoFold, {
	var octo, wL, wR, sigL, sigR;
	octo = In.ar(0, 8);
	wL   = [0.71, 0.5,  0.0,  0.0,  0.35, 0.71, 1.0,  1.0];
	wR   = [0.71, 1.0,  1.0,  0.71, 0.35, 0.0,  0.0,  0.5];
	sigL = Mix.ar(octo * wL);
	sigR = Mix.ar(octo * wR);
	Out.ar(0, [sigL, sigR] * 0.5);
}).add;

~r_foldSynth = nil;

~r_foldStart = {
	~r_foldSynth = Synth(\r_stereoFold, target: s, addAction: \addToTail);
	"● Stereo fold ON".postln;
};

~r_foldStop = {
	if(~r_foldSynth.notNil) { ~r_foldSynth.free; ~r_foldSynth = nil };
	"■ Stereo fold OFF".postln;
};

// ── Recording ────────────────────────────────────────────────────────────
SynthDef(\r_rec, {
	|bufnum=0|
	var sig = Mix.ar(SoundIn.ar([0,1,2,3])) / 4.0;
	DiskOut.ar(bufnum, sig ! 2);
}).add;

~r_recSynth = nil; ~r_recBuf = nil; ~r_recPath = nil;

~r_recStart = {
	var ts   = Date.getDate.format("%Y%m%d_%H%M%S");
	var path = "/Volumes/disk 1/remnant_" ++ ts ++ ".aiff";
	~r_recPath = path;
	~r_recBuf  = Buffer.alloc(s, 65536, 2);
	~r_recBuf.write(path, "AIFF", "float", 0, 0, true);
	~r_recSynth = Synth(\r_rec, [\bufnum, ~r_recBuf.bufnum],
	              target: ~r_gSpat, addAction: \addAfter);
	("● REC → " ++ path).postln;
};

~r_recStop = {
	if(~r_recSynth.notNil) { ~r_recSynth.free; ~r_recSynth = nil };
	if(~r_recBuf.notNil)   { ~r_recBuf.close; ~r_recBuf.free; ~r_recBuf = nil };
	("■ REC stop").postln;
};

// ── Stereo fold for headphones ────────────────────────────────────────────────────
SynthDef(\r_stereoFold, {
	var octo, wL, wR, sigL, sigR;
	octo = In.ar(0, 8);
	wL   = [0.71, 0.5,  0.0,  0.0,  0.35, 0.71, 1.0,  1.0];
	wR   = [0.71, 1.0,  1.0,  0.71, 0.35, 0.0,  0.0,  0.5];
	sigL = Mix.ar(octo * wL);
	sigR = Mix.ar(octo * wR);
	Out.ar(0, [sigL, sigR] * 0.5);
}).add;

~r_foldSynth = nil;
~r_foldStart = { ~r_foldSynth = Synth(\r_stereoFold, target: s, addAction: \addToTail); "● Fold ON".postln };
~r_foldStop  = { if(~r_foldSynth.notNil) { ~r_foldSynth.free; ~r_foldSynth = nil }; "■ Fold OFF".postln };

// ═══════════════════════════════════════════════════════════════════════════
// NanoKONTROL2 MIDI mapping
//
// CC assignments (NanoKONTROL2 default template):
//   Slider 1  (CC 0)  → tension
//   Slider 2  (CC 1)  → master vol
//   Slider 3  (CC 2)  → xfade
//   Slider 4  (CC 3)  → gate thr  (-80 to 0 dB)
//   Slider 5  (CC 4)  → gate rel  (0 to 8 s)
//   Knob 1    (CC 16) → tension (duplicate, finer control)
//   S buttons (CC 32–38) → categories: Klang/Farbklang/Geräusch/Kadenz/Textur/Stille/Neutro
//   Transport ■ (CC 42) → PANIC
//   Transport ● (CC 45) → REC toggle
//   Transport ► (CC 41) → headphone fold toggle
// ─────────────────────────────────────────────────────────────────────────────

~r_midiResponders = [];

~r_midiSetup = {
	var cats = ["Klang","Farbklang","Geräusch","Kadenz","Textur","Stille","Neutro"];
	MIDIClient.init;
	MIDIIn.connectAll;

	// Slider 1 — tension
	~r_midiResponders = ~r_midiResponders.add(
		MIDIFunc.cc({ |val|
			var t = val / 127.0;
			~r_gestTension = t;
			if(~r_setTension.notNil) { ~r_setTension.(t) };
			if(~r_hudTensSlider.notNil) { { ~r_hudTensSlider.value_(t) }.defer };
		}, 0)
	);

	// Knob 1 — tension (CC 16)
	~r_midiResponders = ~r_midiResponders.add(
		MIDIFunc.cc({ |val|
			var t = val / 127.0;
			~r_gestTension = t;
			if(~r_setTension.notNil) { ~r_setTension.(t) };
			if(~r_hudTensSlider.notNil) { { ~r_hudTensSlider.value_(t) }.defer };
		}, 16)
	);

	// Slider 2 — master vol (0–3.0)
	~r_midiResponders = ~r_midiResponders.add(
		MIDIFunc.cc({ |val|
			var v = val / 127.0 * 3.0;
			~r_masterVol = v;
			if(~r_synths.notNil) {
				~r_nFields.do { |i|
					var entry = ~r_synths[i];
					if(entry.notNil and: { entry[2].notNil }) {
						try { entry[2].set("amp", v) };
					};
				};
			};
			if(~r_hudVolSlider.notNil) { { ~r_hudVolSlider.value_(v/3.0) }.defer };
		}, 1)
	);

	// Slider 3 — xfade (0.1–12s)
	~r_midiResponders = ~r_midiResponders.add(
		MIDIFunc.cc({ |val|
			var v = (val / 127.0 * 12.0).max(0.1);
			~r_xfadeTime = v;
			if(~r_hudXfSlider.notNil) { { ~r_hudXfSlider.value_(v/12.0) }.defer };
		}, 2)
	);

	// Slider 4 — gate thr (-80 to 0 dB)
	~r_midiResponders = ~r_midiResponders.add(
		MIDIFunc.cc({ |val|
			var db = ((val / 127.0 * 80.0) - 80.0).round(1);
			~r_gateThresh = db;
			if(~r_gateSynth.notNil) { try { ~r_gateSynth.set("thresh", db) } };
			if(~r_hudThrSlider.notNil) { { ~r_hudThrSlider.value_((db+80)/80) }.defer };
		}, 3)
	);

	// Slider 5 — gate rel (0–8s)
	~r_midiResponders = ~r_midiResponders.add(
		MIDIFunc.cc({ |val|
			var rv = (val / 127.0 * 8.0).round(0.1);
			~r_gateRelease = rv;
			if(~r_gateSynth.notNil) { try { ~r_gateSynth.set("releaseTime", rv) } };
			if(~r_hudRelSlider.notNil) { { ~r_hudRelSlider.value_(rv/8.0) }.defer };
		}, 4)
	);

	// S buttons CC 32–38 — categorie
	cats.do { |cat, i|
		~r_midiResponders = ~r_midiResponders.add(
			MIDIFunc.cc({ |val|
				if(val > 0) {
					var t  = ~r_gestTension ? 0.3;
					var az = ~r_currentAz  ? 180.0;
					~r_gesture.(cat, t, az);
					if(~r_hudCatBtns.notNil) {
						{ ~r_hudCatBtns.do { |b, j| b.value_(if(j==i){1}{0}) } }.defer;
					};
				};
			}, 32 + i)
		);
	};

	// Transport ■ (CC 42) — PANIC
	~r_midiResponders = ~r_midiResponders.add(
		MIDIFunc.cc({ |val|
			if(val > 0) {
				if(~r_panic.notNil) { ~r_panic.() };
				if(~r_hudCatBtns.notNil) { { ~r_hudCatBtns.do { |b| b.value_(0) } }.defer };
			};
		}, 42)
	);

	// Transport ● (CC 45) — REC toggle
	~r_midiResponders = ~r_midiResponders.add(
		MIDIFunc.cc({ |val|
			if(val > 0) {
				if(~r_hudRecBtn.notNil) {
					{ ~r_hudRecBtn.value_(1 - ~r_hudRecBtn.value).doAction }.defer;
				};
			};
		}, 45)
	);

	// Transport ► (CC 41) — headphone fold toggle
	~r_midiResponders = ~r_midiResponders.add(
		MIDIFunc.cc({ |val|
			if(val > 0) {
				if(~r_hudFoldBtn.notNil) {
					{ ~r_hudFoldBtn.value_(1 - ~r_hudFoldBtn.value).doAction }.defer;
				};
			};
		}, 41)
	);

	"NanoKONTROL2 MIDI responders active.".postln;
	"  Sl1=tension  Sl2=vol  Sl3=xfade  Sl4=gate thr  Sl5=gate rel".postln;
	"  S1-7=categories  ■=PANIC  ●=REC  ►=headphones".postln;
};

~r_midiStop = {
	~r_midiResponders.do { |r| r.free };
	~r_midiResponders = [];
	"MIDI responders freed.".postln;
};

// Auto-start MIDI
~r_midiSetup.();

"HUD Block 1 OK — evaluate Block 2 to open window".postln;
)




// ═══════════════════════════════════════════════════════════════════════════
// BLOCK 2 — HUD window  (controllo manuale per performance)
// ═══════════════════════════════════════════════════════════════════════════
(
var win, layout, accentCol, dimCol, fgCol, greenCol, redCol, monoFont, monoSmall;
var sep, catBtns, activeCatLabel;
var tensRow, tensSlider, tensVal;
var flucoBar, flucoVal, flucoRow;
var finalTBar, finalTVal, finalTRow;
var gateMeter, thrRow, thrSlider, thrVal;
var relRow, relSlider, relVal;
var xfRow, xfSlider, xfVal;
var volRow, volSlider, volVal;
var panicBtn, hudRoutine, r, makeSlider;
var catColors, cats, row1, row2;
var recBtn, recLabel, foldBtn;
var midiLabel;

// ── Init variabili ────────────────────────────────────────────────────────────
win       = Window("REMNANT", Rect(20, 20, 280, 650), resizable: false)
            .background_(Color(0.07, 0.07, 0.07, 0.95))
            .alwaysOnTop_(true);
layout    = VLayout();
accentCol = Color(0.22, 0.55, 0.9);
dimCol    = Color(0.45, 0.45, 0.45);
fgCol     = Color.white;
greenCol  = Color(0.2, 0.7, 0.3);
redCol    = Color(0.9, 0.3, 0.1);
monoFont  = Font("Courier New", 10);
monoSmall = Font("Courier New", 9);
catBtns   = Dictionary.new;

catColors = Dictionary[
	"Klang"     -> Color(0.29, 0.56, 0.85),
	"Farbklang" -> Color(0.36, 0.72, 0.36),
	"Geräusch"  -> Color(0.87, 0.36, 0.36),
	"Kadenz"    -> Color(0.73, 0.46, 0.09),
	"Textur"    -> Color(0.61, 0.35, 0.71),
	"Stille"    -> Color(0.6,  0.6,  0.6 ),
	"Neutro"    -> Color(0.45, 0.45, 0.45),
];
cats = ["Klang", "Farbklang", "Geräusch", "Kadenz", "Textur", "Stille", "Neutro"];
row1 = HLayout();
row2 = HLayout();

makeSlider = { |labelStr, knobCol|
	var row = HLayout();
	var lbl = StaticText().string_(labelStr).font_(monoFont)
	          .stringColor_(dimCol).fixedWidth_(88);
	var val = StaticText().string_("—").font_(monoFont)
	          .stringColor_(fgCol).fixedWidth_(36).align_(\right);
	var sl  = Slider().orientation_(\horizontal)
	          .background_(Color(0.15,0.15,0.15))
	          .knobColor_(knobCol ?? accentCol);
	row.margins = [0,0,0,0]; row.spacing = 4;
	row.add(lbl); row.add(sl); row.add(val);
	[row, sl, val]
};
sep = {
	StaticText().string_("─────────────────────────")
	.stringColor_(dimCol).font_(monoFont).align_(\center)
};

win.layout = layout;
layout.margins = [12, 12, 12, 12];
layout.spacing = 5;

// ── Titolo ────────────────────────────────────────────────────────────────────
layout.add(
	StaticText().string_("R E M N A N T")
	.font_(Font("Georgia", 12, italic: true))
	.stringColor_(dimCol).align_(\center)
);

// ── Active category ──────────────────────────────────────────────────────────
activeCatLabel = StaticText()
	.string_("— waiting —")
	.font_(Font("Georgia", 15, italic: true))
	.stringColor_(dimCol).align_(\center);
layout.add(activeCatLabel);

// Aggiorna activeCatLabel quando ~r_gesture viene chiamato esternamente
~r_hudCatDisplay = activeCatLabel;

layout.add(sep.());

// ── Bottoni category (controllo manuale) ─────────────────────────────────────
layout.add(
	StaticText().string_("category")
	.font_(monoSmall).stringColor_(dimCol).align_(\center)
);

row1.margins = [0,0,0,0]; row1.spacing = 3;
row2.margins = [0,0,0,0]; row2.spacing = 3;

cats.do { |cat, i|
	var col = catColors[cat];
	var btn = Button()
		.states_([
			[cat, Color(0.3, 0.3, 0.3), Color(0.12, 0.12, 0.12)],
			[cat, Color(0.07, 0.07, 0.07), col],
		])
		.font_(Font("Courier New", 9, bold: true))
		.fixedHeight_(32);

	btn.action = { |b|
		catBtns.do { |ob| if(ob !== btn) { ob.value_(0) } };
		if(b.value == 1) {
			var t, az, gIdx, gest, evs, ev, evAz, evTen;
			t  = ~r_gestTension ? 0.3;
			az = ~r_currentAz  ? 180.0;
			~r_gesture.(cat, t, az);
			{ activeCatLabel.string_(cat).stringColor_(col) }.defer;

			// Visualizzazione p5.js — avanza all'evento successivo nella score
			gIdx = ~r_timerGestIdx ? 0;
			gest = ~r_hudGestures[gIdx];
			if(gest.notNil) {
				evs = ~r_score["gestures"][gIdx]["events"];
				if(evs.notNil and: { evs.size > 0 }) {
					ev    = evs[~r_vizEventIdx % evs.size];
					evAz  = ev["azimuth"].asFloat;
					evTen = ev["tension"].asFloat;
					~r_vizEventIdx = (~r_vizEventIdx + 1) % evs.size;
					NetAddr("127.0.0.1", 9000).sendMsg("/remnant/category", cat);
					NetAddr("127.0.0.1", 9000).sendMsg("/remnant/event", gIdx, ~r_vizEventIdx, evAz, evTen);
				};
			};
		} {
			{ activeCatLabel.string_("—").stringColor_(dimCol) }.defer;
		};
	};

	catBtns[cat] = btn;
	if(i < 4) { row1.add(btn) } { row2.add(btn) };
};

layout.add(row1);
layout.add(row2);

layout.add(sep.());

// ── Tension ───────────────────────────────────────────────────────────────────
r = makeSlider.("tension", accentCol);
tensRow = r[0]; tensSlider = r[1]; tensVal = r[2];
tensSlider.value_(0.3);
tensVal.string_("0.30");
tensSlider.action = { |sl|
	var t, entry;
	t = sl.value.round(0.01);
	tensVal.string_(t.asString.padLeft(4, "0"));
	~r_hudManualTension = t;
	~r_gestTension = t;
	if(~r_setTension.notNil) {
		~r_setTension.(t);
	} {
		if(~r_synths.notNil) {
			~r_nFields.do { |i|
				entry = ~r_synths[i];
				if(entry.notNil and: { entry[0].notNil }) {
					try { entry[0].set(\tension,
						(~r_gestTension + (~r_flucoTension * 0.4)).clip(0,1)) };
				};
			};
		};
	};
};
layout.add(tensRow);

// ── FluCoMa tension ───────────────────────────────────────────────────────────
flucoRow = HLayout();
flucoRow.margins = [0,0,0,0]; flucoRow.spacing = 4;
flucoBar = UserView()
	.fixedHeight_(10)
	.background_(Color(0.12, 0.12, 0.12))
	.drawFunc_({ |v|
		var fv = flucoBar.getProperty(\flucoVal) ? 0.0;
		var w  = v.bounds.width * fv;
		Pen.color_(Color(fv, 1.0 - fv, 0.2));
		Pen.fillRect(Rect(0, 0, w, v.bounds.height));
	});
flucoBar.setProperty(\flucoVal, 0.0);
flucoVal = StaticText().string_("0.00")
	.font_(monoSmall).stringColor_(Color(0.4, 0.8, 0.3))
	.fixedWidth_(36).align_(\right);
flucoRow.add(StaticText().string_("FluCoMa t")
	.font_(monoSmall).stringColor_(dimCol).fixedWidth_(88));
flucoRow.add(flucoBar);
flucoRow.add(flucoVal);
layout.add(flucoRow);

// ── Final tension ────────────────────────────────────────────────────────────
finalTRow = HLayout();
finalTRow.margins = [0,0,0,0]; finalTRow.spacing = 4;
finalTBar = UserView()
	.fixedHeight_(10)
	.background_(Color(0.12, 0.12, 0.12))
	.drawFunc_({ |v|
		var fv = finalTBar.getProperty(\finalTVal) ? 0.0;
		var w  = v.bounds.width * fv;
		Pen.color_(Color(fv, 0.3, 1.0 - fv));
		Pen.fillRect(Rect(0, 0, w, v.bounds.height));
	});
finalTBar.setProperty(\finalTVal, 0.0);
finalTVal = StaticText().string_("0.00")
	.font_(monoSmall).stringColor_(Color(0.5, 0.3, 0.9))
	.fixedWidth_(36).align_(\right);
finalTRow.add(StaticText().string_("final t")
	.font_(monoSmall).stringColor_(dimCol).fixedWidth_(88));
finalTRow.add(finalTBar);
finalTRow.add(finalTVal);
layout.add(finalTRow);

layout.add(sep.());

// ── Gate meter ────────────────────────────────────────────────────────────────
layout.add(HLayout(
	StaticText().string_("gate").font_(monoFont).stringColor_(dimCol),
	gateMeter = UserView()
		.fixedHeight_(14)
		.background_(Color(0.12, 0.12, 0.12))
		.drawFunc_({ |v|
			var gv  = gateMeter.getProperty(\gateVal) ? 0.0;
			var w   = v.bounds.width * gv;
			var col = if(gv > 0.7) { redCol } { greenCol };
			Pen.color_(col);
			Pen.fillRect(Rect(0, 0, w, v.bounds.height));
		})
));
gateMeter.setProperty(\gateVal, 0.0);

r = makeSlider.("gate thr (dB)", Color(0.6, 0.6, 0.6));
thrRow = r[0]; thrSlider = r[1]; thrVal = r[2];
thrSlider.value_((-42 - (-80)) / 80);
thrVal.string_("-42");
thrSlider.action = { |sl|
	var db;
	db = ((sl.value * 80) - 80).round(1);
	thrVal.string_(db.asString);
	~r_gateThresh = db;
	if(~r_gateSynth.notNil) { try { ~r_gateSynth.set("thresh", db) } };
};
layout.add(thrRow);

r = makeSlider.("gate rel (s)", Color(0.6, 0.6, 0.6));
relRow = r[0]; relSlider = r[1]; relVal = r[2];
relSlider.value_(1.2 / 8.0);
relVal.string_("1.2");
relSlider.action = { |sl|
	var rv;
	rv = (sl.value * 8.0).round(0.1);
	relVal.string_(rv.asString);
	~r_gateRelease = rv;
	if(~r_gateSynth.notNil) { try { ~r_gateSynth.set("releaseTime", rv) } };
};
layout.add(relRow);

layout.add(sep.());

r = makeSlider.("xfade (s)", Color(0.6, 0.6, 0.6));
xfRow = r[0]; xfSlider = r[1]; xfVal = r[2];
xfSlider.value_(2.0 / 12.0);
xfVal.string_("2.0");
xfSlider.action = { |sl|
	var xv;
	xv = (sl.value * 12.0).round(0.1).max(0.1);
	xfVal.string_(xv.asString);
	~r_xfadeTime = xv;
};
layout.add(xfRow);

r = makeSlider.("master vol", Color(0.6, 0.6, 0.6));
volRow = r[0]; volSlider = r[1]; volVal = r[2];
volSlider.value_(1.0 / 3.0);
volVal.string_("1.0");
volSlider.action = { |sl|
	var vv, entry;
	vv = (sl.value * 3.0).round(0.01);
	volVal.string_(vv.asString);
	~r_masterVol = vv;
	if(~r_synths.notNil) {
		~r_nFields.do { |i|
			entry = ~r_synths[i];
			if(entry.notNil and: { entry[2].notNil }) {
				try { entry[2].set(\amp, vv) };
			};
		};
	};
};
layout.add(volRow);

layout.add(sep.());

// ── Headphone monitor ────────────────────────────────────────────────────────────
foldBtn = Button()
	.states_([
		["◎  HEADPHONES",    Color(0.5, 0.5, 0.5), Color(0.12, 0.12, 0.12)],
		["◎  HEADPHONES ON", Color(0.1, 0.1, 0.1), Color(0.5,  0.75, 0.3) ],
	])
	.font_(Font("Courier New", 9, bold: true));
foldBtn.action = { |b| if(b.value == 1) { ~r_foldStart.() } { ~r_foldStop.() } };
layout.add(foldBtn);

// ── REC ───────────────────────────────────────────────────────────────────────
recBtn = Button()
	.states_([
		["● REC",  Color(1.0, 0.3, 0.3), Color(0.18, 0.05, 0.05)],
		["■ STOP", Color(1.0, 0.6, 0.0), Color(0.22, 0.12, 0.0) ],
	])
	.font_(Font("Courier New", 10, bold: true));
recLabel = StaticText()
	.string_("")
	.font_(Font("Courier New", 8))
	.stringColor_(Color(0.45, 0.45, 0.45))
	.align_(\center);
recBtn.action = { |b|
	if(b.value == 1) {
		~r_recStart.();
		{ recLabel.string_("● recording...") }.defer;
	} {
		~r_recStop.();
		{ recLabel.string_("✓ saved to Desktop") }.defer;
	};
};
layout.add(recBtn);
layout.add(recLabel);

// ── PANIC ─────────────────────────────────────────────────────────────────────
panicBtn = Button()
	.states_([["PANIC", Color.red, Color(0.15, 0.05, 0.05)]])
	.font_(Font("Courier New", 10, bold: true))
	.action_({
		if(~r_panic.notNil) { ~r_panic.() };
		catBtns.do { |b| b.value_(0) };
		if(recBtn.value == 1)  { ~r_recStop.();  recBtn.value_(0);  { recLabel.string_("") }.defer };
		if(foldBtn.value == 1) { ~r_foldStop.(); foldBtn.value_(0) };
		{ activeCatLabel.string_("—").stringColor_(dimCol) }.defer;
	});
layout.add(panicBtn);

// ── Refresh routine ────────────────────────────────────────────────────────
hudRoutine = Routine({
	var gv, ft, gt, fin;
	loop {
		0.08.wait;
		gv  = if(~r_gateBus.notNil) { ~r_gateBus.getSynchronous } { 1.0 };
		~r_hudGateLevel = gv;
		ft  = ~r_flucoTension ? 0.0;
		gt  = ~r_gestTension  ? 0.0;
		fin = (gt + (ft * 0.4)).clip(0, 1);
		{
			gateMeter.setProperty(\gateVal, gv); gateMeter.refresh;
			flucoBar.setProperty(\flucoVal, ft); flucoBar.refresh;
			flucoVal.string_(ft.round(0.01).asString);
			finalTBar.setProperty(\finalTVal, fin); finalTBar.refresh;
			finalTVal.string_(fin.round(0.01).asString);
		}.defer;
	};
}).play(AppClock);

win.onClose = {
	hudRoutine.stop;
	if(~r_recSynth.notNil)  { ~r_recStop.()  };
	if(~r_foldSynth.notNil) { ~r_foldStop.() };
	~r_midiStop.();
};

// ── Registra riferimenti globali per MIDI ─────────────────────────────────────
~r_hudTensSlider = tensSlider;
~r_hudVolSlider  = volSlider;
~r_hudXfSlider   = xfSlider;
~r_hudThrSlider  = thrSlider;
~r_hudRelSlider  = relSlider;
~r_hudCatBtns    = cats.collect { |cat| catBtns[cat] };
~r_hudRecBtn     = recBtn;
~r_hudFoldBtn    = foldBtn;
win.front;
"HUD aperto. Clicca una category per attivarla.".postln;
)
