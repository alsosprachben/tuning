// THE HELP: a ? beside every card's name and every titled region (any
// element with data-help="key"), and the HELP key after the card keys. A tap
// opens a sheet: what the region is for, then each button and control by the
// words printed on it, and what it does.
//
// HELP[key] = { title, intro, terms: [[term, meaning] | 'a subheading', ...] }
'use strict';

const HELP = {
  basics: {
    title: 'Using the screen',
    intro: 'The front panel along the top always shows the selected part. The card keys under it choose the card below. Every card has a ? beside its name, and so do the regions inside it.',
    terms: [
      'Touching the controls',
      ['Drag', 'Up or right turns a knob, fader or field up; down or left turns it down.'],
      ['Fine', 'Rest a second finger anywhere off the controls while you drag: the control moves ten times finer.'],
      ['Detent', 'A named position (a centre, 0 dB, triangle, saw or square on a wave knob) holds the value for a moment as you drag past it.'],
      ['Double-tap', 'Puts the control back to the patch\'s own value (or its default).'],
      ['Long-press', 'Opens a sheet to type the exact value.'],
      ['Orange', 'A control drawn in orange has been changed from the patch.'],
      'The card keys',
      ['PARTS', 'Every part: its key range, level, pan, transpose, channel, mute and solo; layer, split and remove parts.'],
      ['LIBRARY', 'Every patch, by family or by search: tap one to play it on the selected part.'],
      ['SYNTH', 'The selected part\'s synth knobs, laid out as the Moog Messenger\'s panel. Only for the synth programs.'],
      ['STOPS', 'The selected part\'s organ: its stops or drawbars, and a tonewheel organ\'s drive.'],
      ['PIANO', 'The pedals, the dampers on the strings, and a key used as the sustain pedal.'],
      ['DRUMS', 'The drum kits and their sounds as pads to play; the user sets.'],
      ['EFFECTS', 'The insertion effect, and the reverb, chorus, delay and EQ every part shares.'],
      ['MATRIX', 'What the wheels, aftertouch and two controllers move on the selected part.'],
      ['TUNING', 'The tuning every part plays in, and the Indian voices\' raga tuning.'],
      ['CONTROL', 'Controls on the screen for what the keyboard lacks, and routes that rewrite the keyboard\'s own.'],
      ['SCENES', 'Presets and scenes to save and bring back; the metronome; GS reset.'],
      ['SETUP', 'MIDI inputs, the Messenger, the sound settings for every part, the room, and quitting.'],
    ],
  },
  display: {
    title: 'The display',
    intro: 'The selected part, how hard the engine is working, and the levels.',
    terms: [
      ['PART', 'The selected part\'s number. ◀ PART and PART ▶ choose another.'],
      ['Name line', 'The program number (a variation after the dot), its family, and the channel it listens on. ALL CH means every channel.'],
      ['CPU', 'How much of each audio block\'s time the engine spends making sound, on average. GPU+CPU when the graphics chip is helping. Near 100% the sound may break up.'],
      ['VOICES', 'How many voices are sounding now.'],
      ['BUILDING', 'The engine is building the sounds for a new patch or tuning; the number is how far along it is. A patch plays when its build is done.'],
      ['UNDERRUNS', 'How many times the sound dropped out because a block was late.'],
      ['RT DROPPED', 'The engine gave up its real-time priority after a block ran away. Restart nvlive to get it back.'],
      'The seven fields',
      ['', 'Tap a field to choose it, then drag it or turn the dial. Double-tap puts it back; long-press to type the value.'],
      ['LEVEL', 'The part\'s level in dB.'],
      ['PAN', 'Left to right: L64 to C (the centre) to R63.'],
      ['REVERB', 'How much of the part goes to the reverb, 0 to 127.'],
      ['CHORUS', 'How much goes to the chorus, 0 to 127.'],
      ['DELAY', 'How much goes to the delay, 0 to 127.'],
      ['KEY', 'Transpose, in semitones (up to two octaves either way).'],
      ['CH', 'The MIDI channel the part listens to; ALL is every channel.'],
      'The meters',
      ['Two long bars', 'The output\'s left and right peaks. Red within 1 dB of the top.'],
      ['1 to 16', 'Each MIDI channel\'s level.'],
    ],
  },
  panel: {
    title: 'The panel keys and the dial',
    intro: 'These act on the selected part.',
    terms: [
      ['◀ PART / PART ▶', 'Select the part before or after.'],
      ['MUTE', 'Silences the selected part (lit while muted). Tap again to hear it.'],
      ['SOLO', 'Only the soloed parts sound (lit while soloed). Tap again to take it out of the solo.'],
      ['PANIC', 'All notes off: every sounding note on every part is let go and fades as if its key were lifted, and notes left stuck with no key are cleared. Use it when a note hangs. Sounds and settings are not changed.'],
      ['The dial', 'Turns the field chosen on the display, a step each 15 degrees. The word under it names the field.'],
    ],
  },
  parts: {
    title: 'Parts',
    intro: 'A part is one sound with its own keys, channel and level. Several parts can share the keyboard: layered (the same keys) or split (different keys).',
    terms: [
      'The keyboard',
      ['Bars under the keys', 'Each part\'s key range. The selected part is lit; a muted or silenced part is dim.'],
      ['Tap a bar', 'Selects that part.'],
      ['Drag a bar\'s end', 'Moves that end of the part\'s range, key by key.'],
      'The buttons',
      ['LAYER', 'Adds a copy of the selected part, with the same keys and channel. Choose another patch for it in the Library to play two sounds at once.'],
      ['SPLIT', 'Cuts the selected part\'s keys in two at the middle. The upper half becomes a new part; choose its sound in the Library.'],
      ['REMOVE', 'Takes the selected part away and lets its notes go. The first part cannot be removed.'],
      'Each part\'s strip',
      ['Name', 'Tap to select the part.'],
      ['level', 'The part\'s level, −30 to +10 dB. Double-tap for 0 dB.'],
      ['pan', 'Left to right. Double-tap for the centre.'],
      ['KEY', 'Transpose in semitones. Double-tap for none.'],
      ['CH', 'The channel it listens to; ALL is every channel.'],
      ['MUTE / SOLO', 'As the panel keys, for this part.'],
      ['VEL / FIXED', 'VEL: how hard you play sets how loud. FIXED: every key sounds the same, as an organ\'s keys do.'],
    ],
  },
  library: {
    title: 'Library',
    intro: 'Every patch, to play on the selected part.',
    terms: [
      ['Families (left)', '★ Favourites, All, the sixteen General MIDI families, Drum kits, and the MT-32\'s and CM-64\'s own tones.'],
      ['Search', 'Type words: a patch shows if its number, name or family has them all. The screen\'s own keys come up: CLEAR empties it, ⌫ takes a letter back, DONE puts the keys away.'],
      ['A tile', 'Tap to play that patch on the selected part. The lit tile is the part\'s patch now; one blinking is still being built.'],
      ['Number', 'The program number, a variation after the dot; KIT and a number for a drum kit.'],
      ['★', 'Keeps the patch in Favourites (saved beside the session).'],
      ['The notes below', 'What the selected part\'s patch is, how sure we are of it, and what it was fitted to.'],
    ],
  },
  synth: {
    title: 'Synth',
    intro: 'The selected part\'s synth, laid out as the Moog Messenger\'s front panel, then the delay. Each section has its own ?. Long-press a knob for its exact value and the Messenger\'s name for it.',
    terms: [
      ['LAYER A / LAYER B', 'A patch made of two synths: which one the knobs show.'],
      ['N CHANGED · BACK TO THE PATCH', 'How many controls you have changed; tap to put them all back. AS THE PATCH when none are.'],
      ['CONTROLS TEST', 'Opens a page of every kind of control, to try them.'],
      ['Orange', 'Changed from the patch. Double-tap a knob, or a switch\'s name, to put it back.'],
    ],
  },
  'synth:LFO 1': {
    title: 'LFO 1',
    intro: 'A slow oscillator that moves one thing up and down by itself.',
    terms: [
      ['LFO 1 rate', 'How fast it moves.'],
      ['Waveshape', 'The shape of the movement: tri (smooth up and down), saw, ramp, square (jumps between two values).'],
      ['LFO 1 depth', 'How far it moves.'],
      ['Destination', 'What it moves: cutoff (the filter), osc 2 freq (oscillator 2\'s pitch), osc 1 wave, sub wave (their shapes).'],
      ['KB reset', 'On: each new key starts the LFO from the beginning.'],
    ],
  },
  'synth:Left hand': {
    title: 'Left hand',
    intro: 'The controls by the wheels: glide, and what the mod wheel brings in through LFO 2. Turn the mod wheel up to hear it.',
    terms: [
      ['Glide', 'How long a note takes to slide to the next one\'s pitch. 0 is no glide.'],
      ['LFO 2 rate', 'How fast LFO 2 moves.'],
      ['Pitch', 'On: the mod wheel brings LFO 2 onto the pitch (vibrato).'],
      ['Cutoff', 'On: onto the filter (wah).'],
      ['Amp', 'On: onto the level (tremolo).'],
    ],
  },
  'synth:Oscillators': {
    title: 'Oscillators',
    intro: 'The two oscillators, 1 and 2, and the sub oscillator an octave under oscillator 1.',
    terms: [
      ['Octave', 'The oscillator\'s octave, in organ feet: 32′ is lowest, 4′ highest.'],
      ['Tune', 'Fine tuning.'],
      ['Sub wave', 'The sub oscillator\'s shape, sweeping smoothly from triangle to square to a narrow pulse.'],
      ['Waveshape', 'The oscillator\'s shape, sweeping smoothly: fold, triangle, saw, square, pulse. The ticks mark triangle, saw and square; the little screen shows the wave.'],
      ['Osc 2 freq', 'Oscillator 2\'s pitch against oscillator 1: in tune at the centre, or a chosen interval for fatter or harmonised sounds.'],
      ['Mod amount', 'How much the mod destination is moved.'],
      ['Sync 1>2', 'On: oscillator 2 restarts with every cycle of oscillator 1, for a hard, tearing tone as osc 2 freq moves.'],
      ['Mod destination', '1>2 FM: oscillator 1 bends oscillator 2\'s pitch at audio speed (bell and metal tones). F env>osc 2 freq, F env>osc 2 wave, F env>sub wave: the filter envelope moves that instead.'],
    ],
  },
  'synth:Mixer': {
    title: 'Mixer',
    intro: 'How much of each source goes into the filter.',
    terms: [
      ['Osc 1', 'Oscillator 1\'s level.'],
      ['Sub osc', 'The sub oscillator\'s level.'],
      ['Osc 2', 'Oscillator 2\'s level.'],
      ['Noise', 'White noise, for breath and percussion.'],
    ],
  },
  'synth:Filter': {
    title: 'Filter',
    intro: 'The filter shapes the brightness of the sound.',
    terms: [
      ['Cutoff', 'Where the filter starts to cut: low is dark, high is bright.'],
      ['EG amount', 'How far the filter envelope opens the filter on each note.'],
      ['Resonance', 'A peak at the cutoff; turned high, it rings and whistles.'],
      ['KB tracking', 'off: the cutoff is the same on every key. 1:1: it rises with the key, so high notes stay as bright as low ones.'],
      ['Mode', '4P LP: a steep low-pass (the classic Moog). 2P LP: a gentler low-pass. BP: band-pass, only the middle. HP: high-pass, only the top.'],
      ['Res bass', 'Puts back the bass that resonance takes away.'],
    ],
  },
  'synth:Envelopes': {
    title: 'Envelopes',
    intro: 'How each note moves over time: the filter envelope (top row) opens the filter, the amplifier envelope (second row) shapes the level.',
    terms: [
      ['Attack', 'How long the note takes to rise when the key goes down.'],
      ['Decay', 'How long it takes to fall to the sustain level.'],
      ['Sustain', 'The level held while the key stays down.'],
      ['Release', 'How long it takes to die away after the key comes up.'],
      ['Multi-trig', 'On: every key restarts the envelopes, even when played legato.'],
      ['F env vel', 'On: playing harder opens the filter envelope further.'],
      ['A env vel', 'Whether playing harder is louder: voice (as the patch has it), off or on.'],
      ['F env loop / A env loop', 'On: the envelope repeats while the key is held, as a rhythmic pulse.'],
    ],
  },
  'synth:Delay': {
    title: 'Delay',
    intro: 'An analog-style echo after the synth.',
    terms: [
      ['On', 'Turns the echo on.'],
      ['Range', 'short or long echo times.'],
      ['Time', 'The time between echoes.'],
      ['Feedback', 'How many echoes: more feedback, more repeats.'],
      ['Mix', 'How loud the echoes are against the dry sound.'],
      ['LFO rate / LFO amount', 'A slow wobble of the echo time, for a chorus-like or tape-like sway.'],
    ],
  },
  stops: {
    title: 'Stops',
    intro: 'The selected part\'s organ. A pipe organ shows its stops by division; a tonewheel organ shows its drawbars and percussion. A part that is not an organ shows organs to put on it.',
    terms: [
      ['A stop', 'Tap to draw it (lit) or put it in. Taps land at once, however fast.'],
      ['16′, 8′, 4′…', 'The pitch in organ feet: 8′ sounds as written, 16′ an octave lower, 4′ an octave higher; 2-2/3′ and 1-3/5′ add the twelfth and the seventeenth.'],
      ['Perc 3rd / Perc 2nd', 'A tonewheel organ\'s percussion: a short ping on the third or second harmonic as each key goes down, voiced two ways, L102 and B3.'],
      ['N of M drawn', 'How many stops are drawn.'],
      ['The notes below', 'Touch a stop for what it is and what it was fitted to.'],
    ],
  },
  drive: {
    title: 'Drive',
    intro: 'A tonewheel organ\'s overdrive: the valve amplifier in front of the rotating speaker. The mod wheel is the swell pedal.',
    terms: [
      ['Drive', '0 is clean; turned up, the organ growls and breaks up. Up to 3.'],
      ['AS THE VOICE (n)', 'The knob is at the voice\'s own drive, n.'],
      ['BACK TO THE VOICE\'S n', 'You have turned it; tap to put the voice\'s own back. Double-tapping the knob does the same.'],
    ],
  },
  piano: {
    title: 'Piano',
    intro: 'The selected part\'s pedals. They show what the keyboard, a file or this screen last sent, and act on the part\'s channel.',
    terms: [
      ['Pedals', 'Soft, sostenuto and sustain, as on a grand piano.'],
      ['Dampers', 'Where each key\'s damper sits on its strings.'],
      ['Pedal key', 'A key on the keyboard that works as the sustain pedal.'],
    ],
  },
  'piano:pedals': {
    title: 'Pedals',
    intro: 'Tap a pedal to press it; tap again to let it up.',
    terms: [
      ['SOFT', 'Una corda: the hammers strike fewer strings, softer and darker.'],
      ['SOSTENUTO', 'Holds up the dampers of only the keys that are down as it goes down; keys played after it are damped as usual.'],
      ['SUSTAIN', 'Drag the fader through its travel. Between up and down the dampers rest lightly on the strings (half pedal).'],
      ['DOWN / HALF / UP', 'Sets the sustain pedal straight to down, halfway or up.'],
    ],
  },
  'piano:dampers': {
    title: 'Dampers',
    intro: 'Each key\'s damper as the sustain pedal leaves it.',
    terms: [
      ['Lifted', 'Off the string: it rings on.'],
      ['Resting lightly', 'Half pedal: loud notes are cut back, the quiet sound rings on.'],
      ['On the strings', 'Damped: the note stops when its key comes up.'],
      ['The line below', 'The pedal values where the dampers leave the strings, by register. The bass dampers are heavier and leave later. The top keys have no dampers.'],
    ],
  },
  'piano:key': {
    title: 'Pedal key',
    intro: 'For a keyboard with no pedal: a key held down works as the sustain pedal.',
    terms: [
      ['Held', 'Holding the key lifts the dampers.'],
      ['Pushed into', 'Pressing harder into the held key (aftertouch) lowers the dampers back onto the strings, for half-pedalling.'],
      ['REMOVE', 'That key plays as a note again.'],
      ['LEARN A KEY', 'Tap it, then press the key you want. Tap again to stop waiting.'],
      ['Sympathetic strings', 'With them on, the first part\'s undamped strings ring with what is played.'],
    ],
  },
  drums: {
    title: 'Drums',
    intro: 'The selected part\'s drum kit as pads, grouped by kind. A part that is not a drum kit can be given one from the list.',
    terms: [
      ['Kits (left)', 'Tap a kit to put it on the selected part.'],
      ['A pad', 'Strikes its sound: higher up the pad is harder. Several fingers can play at once. Pads light as the keyboard or a file plays them.'],
      ['The key', 'Each pad\'s key name and MIDI number.'],
      ['The notes', 'Touch a pad for what it is and what it was fitted to.'],
      ['User Set 1 / 2', 'Kits you build yourself: each key takes its sound from any key of any kit. Touch a pad to choose.'],
    ],
  },
  'drums:user': {
    title: 'A user set\'s key',
    intro: 'Where the touched pad gets its sound.',
    terms: [
      ['The sets (left)', 'Choose the kit to take the sound from.'],
      ['The keys (right)', 'Tap the sound you want. It plays once and the pad keeps it.'],
    ],
  },
  effects: {
    title: 'Effects',
    intro: 'The insertion effect (one effect, for the parts you put on it), and the system effects every part sends to.',
    terms: [
      ['Insertion effect', 'Its type and knobs, and its sends.'],
      ['Reverb / Chorus / Delay / EQ', 'The system effects, on the right. Each part sends to them with its REVERB, CHORUS and DELAY fields.'],
      ['The notes below', 'Touch a type or knob for what that effect is.'],
    ],
  },
  'fx:ins': {
    title: 'Insertion effect',
    intro: 'One effect at a time, used by the parts put on it: a distortion, a rotary speaker, a phaser and so on.',
    terms: [
      ['THIS PART ON IT', 'Puts the selected part through the effect (lit) or takes it off.'],
      ['On it: channels…', 'Which channels go through it now. If it cannot play live, the reason is shown.'],
      ['The families', 'Groups of types: tap one to see its types.'],
      ['A type', 'Tap to use it. 00 Thru is no effect.'],
      ['The knobs', 'The type\'s settings, in the values its manual prints.'],
    ],
  },
  'fx:sends': {
    title: 'Sends from it',
    intro: 'How much of the insertion effect\'s output also goes on to the system effects.',
    terms: [
      ['to Reverb / to Chorus / to Delay', '0 to 127.'],
    ],
  },
  'fx:rev': {
    title: 'Reverb',
    intro: 'The room or hall every part sends to with its REVERB field (CC91).',
    terms: [
      ['Room 1 … Pan Delay', 'The reverb type. Delay and Pan Delay are echoes.'],
      ['Level', 'How loud the reverb is.'],
      ['Time', 'How long it rings.'],
      ['Feedback', 'For the echo types: how many repeats.'],
      ['No GS reverb set', 'Until a file or this card sets one, the reverb is the room chosen on the Setup card.'],
    ],
  },
  'fx:cho': {
    title: 'Chorus',
    intro: 'The shimmer every part sends to with its CHORUS field (CC93).',
    terms: [
      ['Chorus 1 … Short Delay FB', 'The chorus type; Flanger and the short delays are stronger, jet-like or doubling sounds.'],
      ['Pre-LPF', 'Cuts the highs going in, 0 (none) to 7.'],
      ['Level', 'How loud the chorus is.'],
      ['Feedback', 'How much is fed back, for a stronger, ringing sweep.'],
      ['Delay', 'Its delay time.'],
      ['Rate', 'How fast it sweeps.'],
      ['Depth', 'How far it sweeps.'],
    ],
  },
  'fx:dly': {
    title: 'Delay',
    intro: 'The echo every part sends to with its DELAY field (CC94).',
    terms: [
      ['Delay 1 … Pan Repeat', 'The delay type: plain echoes, echoes panned left and right, an echo into the reverb.'],
      ['Pre-LPF', 'Cuts the highs going in, 0 (none) to 7.'],
      ['Time', 'The centre echo\'s time.'],
      ['Ratio L / Ratio R', 'The left and right echoes\' times, as a share of the centre\'s.'],
      ['Level C / L / R', 'Each echo\'s level.'],
      ['Level', 'The delay\'s overall level.'],
      ['Feedback', 'How many repeats.'],
    ],
  },
  'fx:eq': {
    title: 'EQ',
    intro: 'Bass and treble for the whole mix.',
    terms: [
      ['Low', 'The bass control\'s frequency: 200 or 400 Hz.'],
      ['Low gain', 'Bass up or down, ±12 dB.'],
      ['High', 'The treble control\'s frequency: 3 or 6 kHz.'],
      ['High gain', 'Treble up or down, ±12 dB.'],
    ],
  },
  matrix: {
    title: 'Matrix',
    intro: 'What each controller moves on the selected part\'s channel. A row is a controller; a column is what it moves; the knob is how far, at full travel.',
    terms: [
      'The rows (sources)',
      ['Mod wheel / Pitch bend', 'The keyboard\'s wheels.'],
      ['Channel aftertouch', 'Pressing into a held key (the whole keyboard).'],
      ['Poly aftertouch', 'Pressing into each key on its own, where the keyboard sends it.'],
      ['CC1 / CC2', 'Any two knobs or pedals you choose. Tap "is CCn" to type the controller number.'],
      ['LEARN', 'Tap, then move the knob or pedal you want for CC1 or CC2.'],
      'The columns (destinations)',
      ['Pitch / Cutoff / Amplitude', 'Bend the pitch, open the filter, change the level directly.'],
      ['LFO 1 / LFO 2: Rate, Pitch, Filter, Amp', 'The two vibrato LFOs: their speed, and how much they move pitch (vibrato), filter (wah) and level (tremolo).'],
      'The knobs',
      ['Lit', 'Changed from the power-on setting. Double-tap a knob to put it back.'],
      ['A lit row name', 'That controller moves something.'],
      ['Set by a file\'s GM2 messages', 'Settings a file made with GM2 messages: shown, not changed here.'],
    ],
  },
  tuning: {
    title: 'Tuning',
    intro: 'The tuning every part plays in. Tap one and every part\'s sounds are built again in it (the display shows BUILDING); notes already sounding keep the old tuning.',
    terms: [
      ['Concert pitch, A=440', 'Modern pitch. gm2 is the default: equal temperament at A=440, and a file can retune it with its own tuning messages.'],
      ['Baroque pitch, A=415', 'Half a step lower, with the old temperaments.'],
      ['Pure octaves: pipes', 'Tunings with unstretched octaves, for the pipe organ.'],
      ['Indian, every part', 'Every part in a raga tuning.'],
      ['Other systems', 'The rest.'],
      ['Lit / blinking', 'Lit is playing now; blinking is being built.'],
    ],
  },
  'tn:shape': {
    title: 'The tuning\'s shape',
    intro: 'How the chosen tuning differs from equal temperament.',
    terms: [
      ['C4 to B4', 'Each note of the middle octave, in cents (hundredths of a semitone) above or below equal temperament.'],
      ['A0 to C8', 'How far each octave is stretched wider than a pure 2:1, across the keyboard, as a piano tuner stretches.'],
      ['A4 = n Hz', 'The pitch of the A above middle C.'],
    ],
  },
  'tn:east': {
    title: 'Eastern tuning',
    intro: 'The tuning the Indian instruments\' parts play (sitar, shehnai and the rest), while the other parts keep the tuning above.',
    terms: [
      ['Off', 'The Indian instruments play the tuning above.'],
      ['A system', 'The raga tuning system to use.'],
      ['measured ragas…', 'Ragas tuned as measured from recordings.'],
      ['No raga / a raga', 'The raga, which sets each note\'s exact tuning.'],
      ['Sa', 'The key of Sa, the tonic.'],
    ],
  },
  control: {
    title: 'Control',
    intro: 'Controls on the screen for what the keyboard lacks, and routes that change what the keyboard\'s own controls do.',
    terms: [
      ['On-screen controls', 'Pedals, wheels and switches to play from the screen.'],
      ['Routes', 'The keyboard\'s controls rewritten before the engine hears them.'],
    ],
  },
  'ct:strip': {
    title: 'On-screen controls',
    intro: 'Each sends straight to the engine on its channel.',
    terms: [
      ['A fader', 'A continuous control. Pitch bend and aftertouch spring back when you let go.'],
      ['A switch', 'Tap down, tap up (a sustain pedal, for one).'],
      ['A selector', 'The tonewheel organ\'s vibrato and chorus: off, V1–V3, C1–C3.'],
      ['every channel / channel n', 'Where it sends.'],
      ['REMOVE', 'Takes the control off the screen.'],
      ['+ ADD A CONTROL', 'Choose a control to add, on the selected part\'s channel. A lit choice is already there.'],
    ],
  },
  'ct:routes': {
    title: 'Routes',
    intro: 'Each rewrites a control from the keyboard before the engine hears it, such as a key as the sustain pedal, or one knob as another.',
    terms: [
      ['A route\'s line', 'What it takes and what it becomes.'],
      ['REMOVE', 'Takes the route away: that control reaches the engine as it is.'],
    ],
  },
  'ct:new': {
    title: 'A new route',
    intro: 'Choose where it comes from, what it becomes and how, then ADD THE ROUTE.',
    terms: [
      'FROM',
      ['A KEY (LEARN)', 'Tap, then press the key on the keyboard.'],
      ['A CONTROLLER (LEARN)', 'Tap, then move the knob, slider or pedal.'],
      ['WHEEL UP / DOWN / EITHER', 'The pitch wheel pushed up, pulled down, or either way.'],
      ['AFTERTOUCH', 'Pressing into held keys.'],
      'TO',
      ['The controls', 'What it becomes.'],
      'HOW',
      ['KEEP THE ORIGINAL TOO', 'The original still does its own job as well.'],
      ['LATCH (PRESS ON, PRESS OFF)', 'For a switch: one press turns it on, the next off.'],
      ['PUSH INTO IT TO DAMP', 'For a key as the sustain: pressing into it lowers the dampers.'],
      ['EVERY CHANNEL / CHANNEL n', 'Every part, or only the selected part\'s channel.'],
      ['ADD THE ROUTE', 'Adds it. The line beside it says what it will do.'],
    ],
  },
  scenes: {
    title: 'Scenes',
    intro: 'Save the setup and bring it back. Presets and scenes are kept beside the session.',
    terms: [
      ['Presets', 'The whole setup.'],
      ['Scenes', 'Only each channel\'s control settings.'],
      ['Metronome', 'A click to play with.'],
      ['GS reset', 'Everything back to power-on.'],
    ],
  },
  'sc:presets': {
    title: 'Presets',
    intro: 'The whole setup: the parts and their patches, the routes, the tuning and the effects.',
    terms: [
      ['A preset', 'Tap to choose it; its buttons come up. Tap again to put them away.'],
      ['LOAD', 'Brings that setup back.'],
      ['SAVE OVER', 'Saves the setup now in its place.'],
      ['DELETE', 'Takes it away.'],
      ['SAVE THIS SETUP AS…', 'Name a new preset on the screen\'s keys and save the setup now.'],
    ],
  },
  'sc:scenes': {
    title: 'Scenes',
    intro: 'Each channel\'s control settings (levels, pans, sends, pedals), without changing the sounds.',
    terms: [
      ['A scene', 'Tap to choose it; its buttons come up.'],
      ['RECALL', 'Sets the controls as the scene has them.'],
      ['SAVE OVER', 'Saves the controls now in its place.'],
      ['DELETE', 'Takes it away.'],
      ['SAVE THE CONTROLS AS…', 'Name a new scene and save the controls now.'],
    ],
  },
  'sc:metro': {
    title: 'Metronome',
    intro: 'A click from a recorded metronome.',
    terms: [
      ['ON', 'Starts and stops it.'],
      ['Tempo', 'Beats a minute, 30 to 300.'],
      ['Bell every', 'A bell on the first of every n beats, or none.'],
      ['Level', 'How loud, in dB.'],
    ],
  },
  'sc:gs': {
    title: 'GS reset',
    intro: 'As a sequencer\'s GS Reset.',
    terms: [
      ['GS RESET', 'Tap twice within 3 seconds: every part goes back to program 1, and the controllers, effects and receive settings to power-on.'],
    ],
  },
  setup: {
    title: 'Setup',
    intro: 'The rig: inputs, the sound settings for every part, the room. The line at the top is the sample rate and the block size, the time the engine has for each block of sound.',
    terms: [
      ['QUIT CLAVITONE', 'Tap twice within 3 seconds: the engine saves the session and stops, and this window closes. Closing the window does the same.'],
    ],
  },
  'su:midi': {
    title: 'MIDI in',
    intro: 'Every MIDI device plugged in. Several can be on at once; their notes are merged. The choice is kept in the session.',
    terms: [
      ['A device', 'Tap to turn it on or off.'],
      ['reading', 'On and being read.'],
      ['wanted, not open', 'On, but it could not be opened (unplugged, or another program has it).'],
      ['off', 'Not read.'],
    ],
  },
  'su:msgr': {
    title: 'The Messenger',
    intro: 'The Moog Messenger, when one is plugged in.',
    terms: [
      ['On …', 'Which MIDI input it is on.'],
      ['READ ITS KNOBS', 'On: turning the Messenger\'s own knobs turns the same knobs on the Synth card.'],
      ['FIRMWARE BEFORE 1.0.7', 'Turn on if its firmware is older than 1.0.7, which sent the cutoff knob differently.'],
    ],
  },
  'su:sound': {
    title: 'Sound',
    intro: 'Settings every part plays through.',
    terms: [
      ['Master', 'The overall output level.'],
      ['Headroom', 'How much every note is turned down before the mix, so that big chords stay under the limiter.'],
      ['Limiter knee', 'Where the output limiter starts to hold the level back: lower is gentler and earlier.'],
      ['Bend range', 'How far the pitch wheel bends, in semitones.'],
      ['Mod depth', 'How deep the mod wheel\'s vibrato is at full wheel, in cents.'],
      ['Mod rate', 'How much faster the vibrato goes at full wheel.'],
      ['Aftertouch', 'How much louder (and brighter) a held note gets as you press into it, at full pressure.'],
      ['THE GPU', 'On: the graphics chip helps render the sound, for more voices.'],
      ['THE ROOM\'S TAIL', 'On: the room\'s reverb tail.'],
      ['The room', 'The room the instruments play in, when a file or the Effects card has not set a GS reverb.'],
      ['Program changes read as', 'Which Sound Canvas a file\'s program and bank numbers are read for: ours, or the SC-55, SC-88, SC-88Pro or SC-8850\'s own map.'],
    ],
  },
  'su:rubato': {
    title: 'Borrowed time',
    intro: 'With rubato on (nvlive --rubato), when a block of sound is late, the sound already playing is held on and the time is borrowed instead of dropping out. It is given back where no note falls.',
    terms: [
      ['Callbacks that waited', 'How many times time was borrowed.'],
      ['Time held, ever', 'All the time borrowed since the start.'],
      ['Owed now', 'Time borrowed and not yet given back.'],
      ['Time returned', 'Time given back, and in how many cuts.'],
      ['Held by the partials ringing on', 'Time covered by holding the sound that was playing.'],
    ],
  },
};

const Help = (() => {
  function open(key) {
    const h = HELP[key];
    if (!h) return;
    const back = document.createElement('div'); back.className = 'kit-sheet-back';
    const sh = document.createElement('div'); sh.className = 'kit-sheet help-sheet';
    let body = '', inList = false;
    const close = () => (inList ? '</dl>' : '');
    for (const t of h.terms) {
      if (typeof t === 'string') { body += close() + `<h4>${esc(t)}</h4>`; inList = false; continue; }
      if (!inList) { body += '<dl>'; inList = true; }
      body += `<dt>${esc(t[0])}</dt><dd>${esc(t[1])}</dd>`;
    }
    body += close();
    sh.innerHTML = `<h3>${esc(h.title)}</h3>${h.intro ? `<p class="hs-intro">${esc(h.intro)}</p>` : ''}<div class="hs-body">${body}</div>` +
      '<div class="row"><button class="close">Close</button></div>';
    back.appendChild(sh); document.body.appendChild(back);
    const shut = () => back.remove();
    Kit.press(sh.querySelector('.close'), shut);
    back.addEventListener('pointerdown', e => { if (e.target === back) shut(); });
  }
  // a ? on every [data-help] not yet given one: inside a heading after its
  // words, otherwise as the element's last child
  function scan() {
    document.querySelectorAll('[data-help]').forEach(el => {
      if (el.querySelector(':scope > .qh')) return;
      const b = document.createElement('button');
      b.className = 'qh'; b.dataset.kit = '1'; b.textContent = '?'; b.setAttribute('aria-label', 'Help');
      el.appendChild(b);
      Kit.press(b, () => open(el.dataset.help));
    });
  }
  let queued = false;
  new MutationObserver(() => {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => { queued = false; scan(); });
  }).observe(document.body, { childList: true, subtree: true });
  scan();
  return { open, scan };
})();
