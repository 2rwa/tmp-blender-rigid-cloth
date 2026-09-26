# Cloth Wrap on Jelly with Delayed Ball EEVEE

A follow-up to `cloth-drop-jelly-delayed-ball-eevee`.

The previous free cloth eventually slid off the Jelly and reached the floor. This variant deliberately keeps more cloth on the Jelly until the ball arrives, so the delayed ball can visibly push the cloth into the deforming Jelly.

## Changes from the baseline

- cloth footprint reduced from 4.5 x 3.7 to 3.5 x 3.0;
- cloth starts closer to the Jelly at z=3.45;
- lower bending stiffness so it wraps around rounded edges;
- higher cloth/Jelly collision friction;
- one centered ball enlarged to radius 0.50 and mass 2.6;
- ball still releases at frame 49, exactly 2.0 seconds after frame 1;
- rigid solver raised to 10 substeps/frame and 35 iterations.

## Coupling

The stable two-pass approach remains:

1. delayed rigid ball -> live Soft Body Jelly;
2. baked Jelly + baked ball -> Cloth.

The ball does not physically feel the cloth in this baseline. The goal is to establish a reproducible visual contact state before trying a more strongly coupled solve.

## Behavioral validation

In addition to normal movie and bake validation, the report measures:

- fraction of cloth vertices horizontally over the Jelly immediately before release;
- fraction still over the Jelly at ball impact;
- mean height of the cloth center patch before release and at impact;
- resulting center press depth.

The run fails validation if the cloth has already slipped away or if the delayed ball does not press the center patch downward by a measurable amount.
