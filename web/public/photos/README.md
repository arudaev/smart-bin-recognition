# Lead camera frames

`bank-3bins-brown-grey-touching.jpg` is a 720 px downscale of
`01b83ecd-Restm_C3_BCll_2aa1963a` from the predecessor's archive – three
touching containers, oblique, with overlapping wheels. It is the densest bin
frame that exists anywhere in this project: of 466 labelled photographs, 430
hold one bin, 30 hold two, 6 hold three, and none holds four or more.

**Not committed.** `web/public/photos/*.jpg` is gitignored, in line with the
rest of the archive – see the `cv_garbage/` rule in `.gitignore`. The scanner
falls back to a hatched placeholder without it, so the app runs either way.

To restore it after a fresh clone:

```bash
cp cv_garbage/_samples/bank-3bins-brown-grey-touching.jpg web/public/photos/
```

If this repo should be self-contained instead, drop the `web/public/photos/*.jpg`
line from `.gitignore` and commit the file – it is 103 KB.
