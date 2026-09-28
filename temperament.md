# Temperament notes: Cordier, the equal Pythagorean, and the hybrids

Working notes toward a paper. The idea: take Serge Cordier's equal temperament
with pure fifths as the base, and extend it with the proofs and inharmonicity
work he left unfinished. Every number here comes out of `examples/cordier.py`,
in the section given in brackets. Rerun that script, not this page.

## Sources

Serge Cordier (1933–2005) was a French tuner and theorist. He later taught
tuning at the CNR de Montpellier. He found the temperament in 1972, tuning by
ear, from what his teacher Simon Debonne did in practice. The texts below
belong to the association Tempérament Cordier (temperamentcordier.org). Copies
and a working English translation of the 1974 lecture are kept outside the
repo, in `~/Downloads/cordier/`.

- **1974 lecture.** Cordier, *Première conférence*, Groupe d'Acoustique
  Musicale (G.A.M.), Laboratoire d'Acoustique, Université Paris VI (dir. Émile
  Leipp), 8 November 1974. Published in *Bulletin du G.A.M.* no. 75,
  "L'Accordage des instruments à clavier". Reissued 2018, introduction by Paul
  Dubuisson. This is where the temperament is first stated: the discovery on
  p. 32, the definition on p. 33, the tuning procedure on pp. 36–37, and the
  beat rates of five systems in fig. 16, p. 40.
- **1982 book.** Cordier, *Piano bien tempéré et justesse orchestrale*, Paris:
  Buchet-Chastel, 1982. Per the association, he did not want it reprinted:
  later work showed some of its calculations were wrong once inharmonicity is
  taken into account. It is on Calaméo; we have not read it.
- **1991 lecture.** Cordier, "La justesse musicale", Université d'été
  *Technique de la direction de chœur*, Chambon-sur-Lac, 5 September 1991.
  The association publishes an English version, *Perfectly in Tune*.
- **1994 study.** Cordier, *Maîtrise de l'inharmonicité et accord des pianos*
  (written 1994; reissued 2018 by Pascale Lecomte). It measures real strings,
  on a Steinway D and a Rameau 114.
- **1996 congress paper.** Cordier, "Influence de l'inharmonicité sur les
  rapidités d'intervalles", 32nd AFARP congress, Bourg-en-Bresse, May 1996.
- **Klaus Gillessen** is reported by French Wikipedia to have published the
  same temperament independently in 1995. Not yet checked.
- **Ben's equal Pythagorean.** It is the `stretch_interval` in
  `inharmonicity.py`, `EqualPythagorean` in `path.py`, and the `stretch`
  tuner. It came out of the Clavitone work, reached independently of Cordier.
  Its date still needs pinning down.

## 1. The identity: equal Pythagorean = Cordier  [§1]

Keep every fifth pure (3:2) and widen every octave by 1/7 of the Pythagorean
comma, so that 12 fifths equal 7 octaves exactly:

- octave: 2 × ((3/2)¹² / 2⁷)^(1/7) = **1203.3514¢** (+3.3514¢, which is comma/7)
- semitone: **(3/2)^(1/7)** = 100.2793¢
- fifth: 701.9550¢, pure

**The claim.** The Pythagorean chain of fifths, folded into this octave (the
`pyth(v, o, s)` formula), *is* 12-part equal division. The reason: 12 pure
fifths close exactly on 7 stretched octaves, so the fifth generates a cycle
of order 12. Numerically, all eleven steps come out at 100.279¢.

**What Cordier actually wrote.** He derived the octave from comma arithmetic,
in Holder commas: a fifth is 31, an octave 53, and 12 × 31 = 372 against
7 × 53 = 371. He derived the partition as 7 equal semitones inside the pure
fifth F–C (1974, pp. 33 and 36). He states both forms, but never shows that
the chain and the equal division are the same object, and never writes
(3/2)^(1/7). That identity is ours.

## 2. Inharmonicity  [§1, §2]

**The B that would produce the stretch by itself.** If octaves are aligned on
the 2nd partial, B = **0.00129**; on the 3rd partial, B = **0.000484**. A real
grand's middle register (B ≈ 0.0003–0.0005) supplies only part of the stretch,
about 0.9¢ of the 3.35¢ per octave. The treble supplies more than all of it:
+5.6¢ at C6 and +16¢ at C7 under our Steinway model.

**Cordier's measured fifths are consistent with this.** In the 1994 study,
table 12 (Steinway D), the fifth FA3–DO4 (F4–C5 in scientific pitch) has a
fundamental ratio of 1.50053 and beats −0.29/s. His 1974 lecture gives the
same figure, 1.50051 (p. 32).
- Harmonic strings would need 1.49958 to beat at −0.29/s.
- The Steinway B(f) model gives 1.50072, 0.2¢ from his value.
- A constant **B ≈ 0.00025** reproduces 1.50053 exactly. That is a realistic
  value for a 9-foot concert grand, lower than our model's 0.0005–0.0009,
  which is what longer strings should give.

**So 1.5005 is a pure-sounding fifth, not a wide one.** On stiff strings the
upper partials run sharp, so a fifth that is beatless at the partials must
have a fundamental ratio slightly above 3:2.

**Cordier's own model of inharmonicity (1994).** The deviation of partial n
is K(n² − 1). K grows geometrically, by a factor q per semitone. For the
Rameau 114 (a French upright, data from Piano de France's engineer Sabatier),
K = 0.53¢ at A4 = 440 and q = 1.063779478, which works out to B ≈ 0.0006 at
A4. By 1994 his tuning was a "temperament with progressive semitones"
(q′ = 1.0000268 per step): the fifths' ratio rises from 1.49974 at FA2 to
1.50053 at FA3, "restoring the natural fifth progressively over three
octaves".

**Still to do: fit B(f) against all of his table rows.** Tables 12 and
onwards give every note from FA2 to FA3, for both pianos. That fit is the
real test, and it would make a figure.

## 3. The Pleyel tuners' rule, and why the thirds and sixths even out  [§3]

**The rule (1974, p. 32).** Tuners in the Pleyel tradition made the sixth
A♭3–F4 beat at the same rate as the third D♭4–F4. That needs a slightly wide
octave, and it is what put Cordier on the track of pure fifths.

**The rule taken literally.** It overshoots: the octave comes out +8.65¢ and
the fifths +3.09¢ wide, or +3.57¢ with Steinway inharmonicity. It is not what
yields pure fifths. Cordier's own procedure (pp. 36–37) sets the partition by
a pure fifth. The only equal beat rates it uses are ones that hold *exactly*
under pure fifths, e.g. F–A♭ beating like A♭–C.

**The closed form.** The sixth is the third plus the fourth between the
sixth's lower note and the third's lower note. With d = each interval's
tempering in cents:

  **sixth rate ÷ third rate = ¾ (1 + d₄ / d₃)**

The two beat equally when the fourth is widened by one third of the third's
widening.

| System | d₃ | d₄ | Ratio | Sixth, third (beats/s, at F4) |
|---|---|---|---|---|
| Pure fourth | | 0 | 0.75 | |
| ET | +13.69¢ | +1.96¢ | 0.857 | 9.42, 11.00 |
| Cordier | +14.80¢ | **+3.35¢** (the octave's stretch) | 0.920 | 10.93, 11.89 |
| Equal beating | | about +5.5¢ | 1.000 | 13.31, 13.31 |

**The new observation.** Pure fifths make the thirds and sixths beat in
nearly uniform proportion. In ET they don't, because its fourth is tempered
too little. Under pure fifths the fourth's widening *is* the octave stretch.

## 4. What pure fifths do to every interval  [§4, §5]

Tempering at the coinciding partials, from C4, in cents:

| | 2nd | m3 | M3 | 4th | 5th | M6 | 8ve |
|---|---|---|---|---|---|---|---|
| ET, harmonic | −3.91 | −15.64 | +13.69 | +1.96 | −1.96 | +15.64 | 0 |
| Cordier, harmonic | −3.35 | −14.80 | +14.80 | +3.35 | 0 | +18.15 | +3.35 |
| ET, Steinway | −6.04 | −17.21 | +12.49 | +0.89 | −2.88 | +13.02 | −0.92 |
| Cordier, Steinway | −5.47 | −16.36 | +13.61 | +2.29 | −0.92 | +15.54 | +2.43 |

The Steinway rows keep the fundamentals at exactly 3:2. Tuned beatless by ear,
Cordier's intervals move 0.1–0.9¢ wider still.

- **Better:** the fifth becomes pure, and the 2nd and the minor third improve
  by about 0.5–0.9¢.
- **Wider:** the fourth, the major third and the major sixth. Their beats are
  faster, but the thirds and sixths keep the uniform proportion of §3.
- **The fourth is the cost.** It is ET's +0.89¢ against Cordier's +2.29¢ on
  real strings. It is rarely exposed, though. In a second-inversion F major
  (C4–F4–A4), the fourth beats about 1.4/s, under a third at 13.4/s and a
  sixth at 11.9/s. The trade: tempering comes off the most exposed interval,
  the fifth, and goes onto one that is usually covered.
- **Perception (to be stated as a claim, not derived).** Cordier (p. 35,
  citing Van Esbroeck and Monfort) says a slightly *small* interval sounds
  false and a slightly *large* one sounds pure. His system makes the fifth
  pure and every other deviating interval wide, except the 2nd and the minor
  third. The masking of the fourth is a perceptual claim too: grounded in the
  beat rates, but still to be tested by listening.

## 5. Two chains of pure fifths and a bridge third: hybrid, hybridmean  [§6]

**The construction.** Two chains of pure fifths, joined by one bridge third
X. The comma then lands on the two fifths between the chains, and X alone
sets how it splits. This is Helmholtz's two-chain idea folded into 12 notes.

| Bridge X | Gap fifths | Thirds | RMS from ET |
|---|---|---|---|
| Pure 5:4 (`hybrid`) | −21.51 and −1.95 (a wolf) | 0 to +21.5 | 5.9¢ |
| √(5/4 · 81/64) = 397.07¢ (`hybridmean`) | −10.75 and −12.71: half a syntonic comma each, the second plus a schisma | +8.8 to +21.5 | **3.4¢** |
| ET 400¢ | −7.82 and −15.64 | +5.9 to +21.5 | 3.9¢ |

**An invariant.** In any closed 12-note tuning with pure octaves, the major
thirds average +13.69¢ and the fifths −1.955¢, exactly ET's. A temperament
only chooses where the comma goes.

**hybridmean:**
- Ben's bridge is the geometric mean of the pure and the Pythagorean third,
  which is also ⅛-comma meantone's third.
- It makes eight of the twelve thirds nearly alike, with no wolf.
- It sits closer to ET than Werckmeister III (3.4¢ against 3.6¢ RMS) while
  tempering only two fifths.
- Tuning it by ear needs one reference, the mean third, from two forks or a
  monochord. Everything else is beatless.

**hybridmeanpiano.** The same construction, built in `path.py`
(`HybridMeanNotes`) with octaves on the string's 2nd partial. The bridge
reaches chain two the long way round, which is Ben's path: D4 → F♯4 →
(pure 5th) C♯5 → C♯4 → C♯3, crossing two stretched octaves. The octave
stretch takes part of the comma, the Cordier effect:
- the gap fifths ease to −8.7 and −7.3;
- the eight bridged thirds draw together, from +10.8 to +12.6;
- the result is 2.4¢ RMS from a stretched ET.

The shorter path, a 4th down from F♯4 to C♯4, gave 2.6¢ and a wider spread
of the bridged thirds, +9.8 to +13.6.

**StretchedHelmholtz** (`stretchedhelmholtz`, `StretchedHelmholtzNotes`) has
no bridge third at all:
- chain two: F♯2 → C♯3 → … → C6, pure 5ths;
- three inharmonic octaves back down, C6 → C3;
- chain one: C3 → … → B5, pure 5ths.

F♯ hangs from chain two, a pure 5th below C♯3, so every note is reached by a
beatless 5th or octave. On pipes this would be Pythagorean tuning with the
comma on B–F♯, and the thirds on A, E and B would be Helmholtz's schismatic
diminished 4ths. On a piano the three wrap octaves take about 8¢ of the comma.
At C4:
- major thirds D +2.4, A +3.0, E +3.5 and B +4.8; the others +18.6 to +20.7;
- B–F♯ −15.6, the one tempered fifth;
- 4.6¢ RMS from ET.

It only works *because of* inharmonicity. Hanging F♯ from B instead gives D
major +16.5, which is why F♯ hangs from C♯ for D-minor music.

**Contrapunctus 1 A/B** (`examples/temperament_ab.py`): the grand in the
chamber room, rendered on `hybrid440`, `hybrid440@D`, `hybridmeanpiano` and
`stretchedhelmholtz`. Ben: "They all sound good, actually."

**On pipes, where the partials are harmonic.** Nothing hides a wolf there. A
piano hides one mostly by *decay*; inharmonicity only moves a fifth's beating
partials by about a cent. BuxWV 161 is the case study:
- A–E is 28.6% of all the sounding fifths.
- `hybridmean:466` is what the render uses. Ben's verdict: "The A major and
  D major sound good, like a recording. Just enough tempering."

**Related, not yet checked against primary sources:**
- **Kirnberger II:** the same ingredients as hybridmean (two half-comma
  fifths and a schisma), placed side by side.
- **Kirnberger I:** the hybrid's structure.
- **Werckmeister III, Vallotti, Young:** the other nearly-even well
  temperaments.
- **Helmholtz's schismatic temperament and 24-note harmonium:** near-pure
  fifths and pure octaves, with the thirds taken from diminished fourths.

## 6. The Pleyel temperament, projected  (`pleyel.py`)

The traditional aural method, simulated on a given piano's B(f). It follows
Cordier 1974 pp. 31–32 and 1996:
- A3 comes from the fork.
- The partition F3–F4 is set so its 9 thirds and 4 sixths beat at the
  textbook rates, those of ET on harmonic strings.
- Upward, a 10th beats like the third on the same bass (a 4:2 octave).
- Downward, octaves are beatless.

On harmonic strings the procedure reproduces ET exactly. On the Steinway
model:

| | Result |
|---|---|
| Partition | F3 174.57, C♯4 277.31, F4 349.62. Cordier's 1996 hand calculation: 174.4, 277.3, 349.5. |
| Octave stretch | +2.4 / +4.4 / +9.7 / +21.8¢ (F3 / A4 / A5 / A6) |
| Fifths, at the partials | about −1.7¢ on average (ET on the same strings: −2.9) |

So tuning by the textbook rates on real strings widens the octave, as
Cordier says. But it takes the fifths only about halfway to pure. His "the
fifth becomes pure again" (1996) was computed from fundamentals. To get pure
fifths the tuner has to make them beatless deliberately, as Debonne did.

Two more things the projection shows:
- **The Pleyel sixth** (A♭–F beating like D♭–F), imposed on top of the
  textbook rates, makes the partition's fifths less even.
- **A same-bass 10th/17th rule cannot tune the bass:** the bass note's own
  partial cancels out of the comparison.

**A table is valid only on the piano it was projected for.** Rendered on
another voice, it must be re-projected with that voice's B(f).

## Open

1. Fit B(f) to Cordier's 1994 tables, Steinway D and Rameau 114, row by row.
2. Translate the 1994 study and the 1996 congress paper. They are the
   inharmonicity work we extend.
3. Read the derivation of 1.50051 in the 1982 book.
4. Check Gillessen 1995, Kirnberger, Werckmeister and Helmholtz against
   primary sources.
5. Settle the date of the Clavitone work, for priority.
