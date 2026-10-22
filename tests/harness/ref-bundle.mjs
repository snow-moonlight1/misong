// Test-only reference bundle (esbuild) used to check interoperability of
// src/nde/encoders/hajimi.py. Not shipped in the Python package.
// Contains:
//   hachimi-wonameruto-translator src/lib/hachimiTranslator.ts
//     https://github.com/Starpuccino/hachimi-wonameruto-translator
//     MIT License, Copyright (c) 2025 Starpuccino
//   fflate 0.8.3  https://github.com/101arrowz/fflate
//     MIT License, Copyright (c) 2026 Arjun Barrett
// Full license texts: THIRD_PARTY_NOTICES.md in the repository root.
// node_modules/fflate/esm/index.mjs
import { createRequire } from "module";
var require2 = createRequire("/");
var Worker;
try {
  Worker = require2("worker_threads").Worker;
} catch (e) {
}
var u8 = Uint8Array;
var u16 = Uint16Array;
var i32 = Int32Array;
var fleb = new u8([
  0,
  0,
  0,
  0,
  0,
  0,
  0,
  0,
  1,
  1,
  1,
  1,
  2,
  2,
  2,
  2,
  3,
  3,
  3,
  3,
  4,
  4,
  4,
  4,
  5,
  5,
  5,
  5,
  0,
  /* unused */
  0,
  0,
  /* impossible */
  0
]);
var fdeb = new u8([
  0,
  0,
  0,
  0,
  1,
  1,
  2,
  2,
  3,
  3,
  4,
  4,
  5,
  5,
  6,
  6,
  7,
  7,
  8,
  8,
  9,
  9,
  10,
  10,
  11,
  11,
  12,
  12,
  13,
  13,
  /* unused */
  0,
  0
]);
var clim = new u8([16, 17, 18, 0, 8, 7, 9, 6, 10, 5, 11, 4, 12, 3, 13, 2, 14, 1, 15]);
var freb = function(eb, start) {
  var b = new u16(31);
  for (var i = 0; i < 31; ++i) {
    b[i] = start += 1 << eb[i - 1];
  }
  var r = new i32(b[30]);
  for (var i = 1; i < 30; ++i) {
    for (var j = b[i]; j < b[i + 1]; ++j) {
      r[j] = j - b[i] << 5 | i;
    }
  }
  return { b, r };
};
var _a = freb(fleb, 2);
var fl = _a.b;
var revfl = _a.r;
fl[28] = 258, revfl[258] = 28;
var _b = freb(fdeb, 0);
var fd = _b.b;
var revfd = _b.r;
var rev = new u16(32768);
for (i = 0; i < 32768; ++i) {
  x = (i & 43690) >> 1 | (i & 21845) << 1;
  x = (x & 52428) >> 2 | (x & 13107) << 2;
  x = (x & 61680) >> 4 | (x & 3855) << 4;
  rev[i] = ((x & 65280) >> 8 | (x & 255) << 8) >> 1;
}
var x;
var i;
var hMap = (function(cd, mb, r) {
  var s = cd.length;
  var i = 0;
  var l = new u16(mb);
  for (; i < s; ++i) {
    if (cd[i])
      ++l[cd[i] - 1];
  }
  var le = new u16(mb);
  for (i = 1; i < mb; ++i) {
    le[i] = le[i - 1] + l[i - 1] << 1;
  }
  var co;
  if (r) {
    co = new u16(1 << mb);
    var rvb = 15 - mb;
    for (i = 0; i < s; ++i) {
      if (cd[i]) {
        var sv = i << 4 | cd[i];
        var r_1 = mb - cd[i];
        var v = le[cd[i] - 1]++ << r_1;
        for (var m = v | (1 << r_1) - 1; v <= m; ++v) {
          co[rev[v] >> rvb] = sv;
        }
      }
    }
  } else {
    co = new u16(s);
    for (i = 0; i < s; ++i) {
      if (cd[i]) {
        co[i] = rev[le[cd[i] - 1]++] >> 15 - cd[i];
      }
    }
  }
  return co;
});
var flt = new u8(288);
for (i = 0; i < 144; ++i)
  flt[i] = 8;
var i;
for (i = 144; i < 256; ++i)
  flt[i] = 9;
var i;
for (i = 256; i < 280; ++i)
  flt[i] = 7;
var i;
for (i = 280; i < 288; ++i)
  flt[i] = 8;
var i;
var fdt = new u8(32);
for (i = 0; i < 32; ++i)
  fdt[i] = 5;
var i;
var flm = /* @__PURE__ */ hMap(flt, 9, 0);
var flrm = /* @__PURE__ */ hMap(flt, 9, 1);
var fdm = /* @__PURE__ */ hMap(fdt, 5, 0);
var fdrm = /* @__PURE__ */ hMap(fdt, 5, 1);
var max = function(a) {
  var m = a[0];
  for (var i = 1; i < a.length; ++i) {
    if (a[i] > m)
      m = a[i];
  }
  return m;
};
var bits = function(d, p, m) {
  var o = p / 8 | 0;
  return (d[o] | d[o + 1] << 8) >> (p & 7) & m;
};
var bits16 = function(d, p) {
  var o = p / 8 | 0;
  return (d[o] | d[o + 1] << 8 | d[o + 2] << 16) >> (p & 7);
};
var shft = function(p) {
  return (p + 7) / 8 | 0;
};
var slc = function(v, s, e) {
  if (s == null || s < 0)
    s = 0;
  if (e == null || e > v.length)
    e = v.length;
  return new u8(v.subarray(s, e));
};
var ec = [
  "unexpected EOF",
  "invalid block type",
  "invalid length/literal",
  "invalid distance",
  "stream finished",
  "no stream handler",
  ,
  "no callback",
  "invalid UTF-8 data",
  "extra field too long",
  "date not in range 1980-2099",
  "filename too long",
  "stream finishing",
  "invalid zip data"
  // determined by unknown compression method
];
var err = function(ind, msg, nt) {
  var e = new Error(msg || ec[ind]);
  e.code = ind;
  if (Error.captureStackTrace)
    Error.captureStackTrace(e, err);
  if (!nt)
    throw e;
  return e;
};
var inflt = function(dat, st, buf, dict) {
  var sl = dat.length, dl = dict ? dict.length : 0;
  if (!sl || st.f && !st.l)
    return buf || new u8(0);
  var noBuf = !buf;
  var resize = noBuf || st.i != 2;
  var noSt = st.i;
  if (noBuf)
    buf = new u8(sl * 3);
  var cbuf = function(l2) {
    var bl = buf.length;
    if (l2 > bl) {
      var nbuf = new u8(Math.max(bl * 2, l2));
      nbuf.set(buf);
      buf = nbuf;
    }
  };
  var final = st.f || 0, pos = st.p || 0, bt = st.b || 0, lm = st.l, dm = st.d, lbt = st.m, dbt = st.n;
  var tbts = sl * 8;
  do {
    if (!lm) {
      final = bits(dat, pos, 1);
      var type = bits(dat, pos + 1, 3);
      pos += 3;
      if (!type) {
        var s = shft(pos) + 4, l = dat[s - 4] | dat[s - 3] << 8, t = s + l;
        if (t > sl) {
          if (noSt)
            err(0);
          break;
        }
        if (resize)
          cbuf(bt + l);
        buf.set(dat.subarray(s, t), bt);
        st.b = bt += l, st.p = pos = t * 8, st.f = final;
        continue;
      } else if (type == 1)
        lm = flrm, dm = fdrm, lbt = 9, dbt = 5;
      else if (type == 2) {
        var hLit = bits(dat, pos, 31) + 257, hcLen = bits(dat, pos + 10, 15) + 4;
        var tl = hLit + bits(dat, pos + 5, 31) + 1;
        pos += 14;
        var ldt = new u8(tl);
        var clt = new u8(19);
        for (var i = 0; i < hcLen; ++i) {
          clt[clim[i]] = bits(dat, pos + i * 3, 7);
        }
        pos += hcLen * 3;
        var clb = max(clt), clbmsk = (1 << clb) - 1;
        var clm = hMap(clt, clb, 1);
        for (var i = 0; i < tl; ) {
          var r = clm[bits(dat, pos, clbmsk)];
          pos += r & 15;
          var s = r >> 4;
          if (s < 16) {
            ldt[i++] = s;
          } else {
            var c = 0, n = 0;
            if (s == 16)
              n = 3 + bits(dat, pos, 3), pos += 2, c = ldt[i - 1];
            else if (s == 17)
              n = 3 + bits(dat, pos, 7), pos += 3;
            else if (s == 18)
              n = 11 + bits(dat, pos, 127), pos += 7;
            while (n--)
              ldt[i++] = c;
          }
        }
        var lt = ldt.subarray(0, hLit), dt = ldt.subarray(hLit);
        lbt = max(lt);
        dbt = max(dt);
        lm = hMap(lt, lbt, 1);
        dm = hMap(dt, dbt, 1);
      } else
        err(1);
      if (pos > tbts) {
        if (noSt)
          err(0);
        break;
      }
    }
    if (resize)
      cbuf(bt + 131072);
    var lms = (1 << lbt) - 1, dms = (1 << dbt) - 1;
    var lpos = pos;
    for (; ; lpos = pos) {
      var c = lm[bits16(dat, pos) & lms], sym = c >> 4;
      pos += c & 15;
      if (pos > tbts) {
        if (noSt)
          err(0);
        break;
      }
      if (!c)
        err(2);
      if (sym < 256)
        buf[bt++] = sym;
      else if (sym == 256) {
        lpos = pos, lm = null;
        break;
      } else {
        var add = sym - 254;
        if (sym > 264) {
          var i = sym - 257, b = fleb[i];
          add = bits(dat, pos, (1 << b) - 1) + fl[i];
          pos += b;
        }
        var d = dm[bits16(dat, pos) & dms], dsym = d >> 4;
        if (!d)
          err(3);
        pos += d & 15;
        var dt = fd[dsym];
        if (dsym > 3) {
          var b = fdeb[dsym];
          dt += bits16(dat, pos) & (1 << b) - 1, pos += b;
        }
        if (pos > tbts) {
          if (noSt)
            err(0);
          break;
        }
        if (resize)
          cbuf(bt + 131072);
        var end = bt + add;
        if (bt < dt) {
          var shift = dl - dt, dend = Math.min(dt, end);
          if (shift + bt < 0)
            err(3);
          for (; bt < dend; ++bt)
            buf[bt] = dict[shift + bt];
        }
        for (; bt < end; ++bt)
          buf[bt] = buf[bt - dt];
      }
    }
    st.l = lm, st.p = lpos, st.b = bt, st.f = final;
    if (lm)
      final = 1, st.m = lbt, st.d = dm, st.n = dbt;
  } while (!final);
  return bt != buf.length && noBuf ? slc(buf, 0, bt) : buf.subarray(0, bt);
};
var wbits = function(d, p, v) {
  v <<= p & 7;
  var o = p / 8 | 0;
  d[o] |= v;
  d[o + 1] |= v >> 8;
};
var wbits16 = function(d, p, v) {
  v <<= p & 7;
  var o = p / 8 | 0;
  d[o] |= v;
  d[o + 1] |= v >> 8;
  d[o + 2] |= v >> 16;
};
var hTree = function(d, mb) {
  var t = [];
  for (var i = 0; i < d.length; ++i) {
    if (d[i])
      t.push({ s: i, f: d[i] });
  }
  var s = t.length;
  var t2 = t.slice();
  if (!s)
    return { t: et, l: 0 };
  if (s == 1) {
    var v = new u8(t[0].s + 1);
    v[t[0].s] = 1;
    return { t: v, l: 1 };
  }
  t.sort(function(a, b) {
    return a.f - b.f;
  });
  t.push({ s: -1, f: 25001 });
  var l = t[0], r = t[1], i0 = 0, i1 = 1, i2 = 2;
  t[0] = { s: -1, f: l.f + r.f, l, r };
  while (i1 != s - 1) {
    l = t[t[i0].f < t[i2].f ? i0++ : i2++];
    r = t[i0 != i1 && t[i0].f < t[i2].f ? i0++ : i2++];
    t[i1++] = { s: -1, f: l.f + r.f, l, r };
  }
  var maxSym = t2[0].s;
  for (var i = 1; i < s; ++i) {
    if (t2[i].s > maxSym)
      maxSym = t2[i].s;
  }
  var tr = new u16(maxSym + 1);
  var mbt = ln(t[i1 - 1], tr, 0);
  if (mbt > mb) {
    var i = 0, dt = 0;
    var lft = mbt - mb, cst = 1 << lft;
    t2.sort(function(a, b) {
      return tr[b.s] - tr[a.s] || a.f - b.f;
    });
    for (; i < s; ++i) {
      var i2_1 = t2[i].s;
      if (tr[i2_1] > mb) {
        dt += cst - (1 << mbt - tr[i2_1]);
        tr[i2_1] = mb;
      } else
        break;
    }
    dt >>= lft;
    while (dt > 0) {
      var i2_2 = t2[i].s;
      if (tr[i2_2] < mb)
        dt -= 1 << mb - tr[i2_2]++ - 1;
      else
        ++i;
    }
    for (; i >= 0 && dt; --i) {
      var i2_3 = t2[i].s;
      if (tr[i2_3] == mb) {
        --tr[i2_3];
        ++dt;
      }
    }
    mbt = mb;
  }
  return { t: new u8(tr), l: mbt };
};
var ln = function(n, l, d) {
  return n.s == -1 ? Math.max(ln(n.l, l, d + 1), ln(n.r, l, d + 1)) : l[n.s] = d;
};
var lc = function(c) {
  var s = c.length;
  while (s && !c[--s])
    ;
  var cl = new u16(++s);
  var cli = 0, cln = c[0], cls = 1;
  var w = function(v) {
    cl[cli++] = v;
  };
  for (var i = 1; i <= s; ++i) {
    if (c[i] == cln && i != s)
      ++cls;
    else {
      if (!cln && cls > 2) {
        for (; cls > 138; cls -= 138)
          w(32754);
        if (cls > 2) {
          w(cls > 10 ? cls - 11 << 5 | 28690 : cls - 3 << 5 | 12305);
          cls = 0;
        }
      } else if (cls > 3) {
        w(cln), --cls;
        for (; cls > 6; cls -= 6)
          w(8304);
        if (cls > 2)
          w(cls - 3 << 5 | 8208), cls = 0;
      }
      while (cls--)
        w(cln);
      cls = 1;
      cln = c[i];
    }
  }
  return { c: cl.subarray(0, cli), n: s };
};
var clen = function(cf, cl) {
  var l = 0;
  for (var i = 0; i < cl.length; ++i)
    l += cf[i] * cl[i];
  return l;
};
var wfblk = function(out, pos, dat) {
  var s = dat.length;
  var o = shft(pos + 2);
  out[o] = s & 255;
  out[o + 1] = s >> 8;
  out[o + 2] = out[o] ^ 255;
  out[o + 3] = out[o + 1] ^ 255;
  for (var i = 0; i < s; ++i)
    out[o + i + 4] = dat[i];
  return (o + 4 + s) * 8;
};
var wblk = function(dat, out, final, syms, lf, df, eb, li, bs, bl, p) {
  wbits(out, p++, final);
  ++lf[256];
  var _a2 = hTree(lf, 15), dlt = _a2.t, mlb = _a2.l;
  var _b2 = hTree(df, 15), ddt = _b2.t, mdb = _b2.l;
  var _c = lc(dlt), lclt = _c.c, nlc = _c.n;
  var _d = lc(ddt), lcdt = _d.c, ndc = _d.n;
  var lcfreq = new u16(19);
  for (var i = 0; i < lclt.length; ++i)
    ++lcfreq[lclt[i] & 31];
  for (var i = 0; i < lcdt.length; ++i)
    ++lcfreq[lcdt[i] & 31];
  var _e = hTree(lcfreq, 7), lct = _e.t, mlcb = _e.l;
  var nlcc = 19;
  for (; nlcc > 4 && !lct[clim[nlcc - 1]]; --nlcc)
    ;
  var flen = bl + 5 << 3;
  var ftlen = clen(lf, flt) + clen(df, fdt) + eb;
  var dtlen = clen(lf, dlt) + clen(df, ddt) + eb + 14 + 3 * nlcc + clen(lcfreq, lct) + 2 * lcfreq[16] + 3 * lcfreq[17] + 7 * lcfreq[18];
  if (bs >= 0 && flen <= ftlen && flen <= dtlen)
    return wfblk(out, p, dat.subarray(bs, bs + bl));
  var lm, ll, dm, dl;
  wbits(out, p, 1 + (dtlen < ftlen)), p += 2;
  if (dtlen < ftlen) {
    lm = hMap(dlt, mlb, 0), ll = dlt, dm = hMap(ddt, mdb, 0), dl = ddt;
    var llm = hMap(lct, mlcb, 0);
    wbits(out, p, nlc - 257);
    wbits(out, p + 5, ndc - 1);
    wbits(out, p + 10, nlcc - 4);
    p += 14;
    for (var i = 0; i < nlcc; ++i)
      wbits(out, p + 3 * i, lct[clim[i]]);
    p += 3 * nlcc;
    var lcts = [lclt, lcdt];
    for (var it = 0; it < 2; ++it) {
      var clct = lcts[it];
      for (var i = 0; i < clct.length; ++i) {
        var len = clct[i] & 31;
        wbits(out, p, llm[len]), p += lct[len];
        if (len > 15)
          wbits(out, p, clct[i] >> 5 & 127), p += clct[i] >> 12;
      }
    }
  } else {
    lm = flm, ll = flt, dm = fdm, dl = fdt;
  }
  for (var i = 0; i < li; ++i) {
    var sym = syms[i];
    if (sym > 255) {
      var len = sym >> 18 & 31;
      wbits16(out, p, lm[len + 257]), p += ll[len + 257];
      if (len > 7)
        wbits(out, p, sym >> 23 & 31), p += fleb[len];
      var dst = sym & 31;
      wbits16(out, p, dm[dst]), p += dl[dst];
      if (dst > 3)
        wbits16(out, p, sym >> 5 & 8191), p += fdeb[dst];
    } else {
      wbits16(out, p, lm[sym]), p += ll[sym];
    }
  }
  wbits16(out, p, lm[256]);
  return p + ll[256];
};
var deo = /* @__PURE__ */ new i32([65540, 131080, 131088, 131104, 262176, 1048704, 1048832, 2114560, 2117632]);
var et = /* @__PURE__ */ new u8(0);
var dflt = function(dat, lvl, plvl, pre, post, st) {
  var s = st.z || dat.length;
  var o = new u8(pre + s + 5 * (1 + Math.ceil(s / 7e3)) + post);
  var w = o.subarray(pre, o.length - post);
  var lst = st.l;
  var pos = (st.r || 0) & 7;
  if (lvl) {
    if (pos)
      w[0] = st.r >> 3;
    var opt = deo[lvl - 1];
    var n = opt >> 13, c = opt & 8191;
    var msk_1 = (1 << plvl) - 1;
    var prev = st.p || new u16(32768), head = st.h || new u16(msk_1 + 1);
    var bs1_1 = Math.ceil(plvl / 3), bs2_1 = 2 * bs1_1;
    var hsh = function(i2) {
      return (dat[i2] ^ dat[i2 + 1] << bs1_1 ^ dat[i2 + 2] << bs2_1) & msk_1;
    };
    var syms = new i32(25e3);
    var lf = new u16(288), df = new u16(32);
    var lc_1 = 0, eb = 0, i = st.i || 0, li = 0, wi = st.w || 0, bs = 0;
    for (; i + 2 < s; ++i) {
      var hv = hsh(i);
      var imod = i & 32767, pimod = head[hv];
      prev[imod] = pimod;
      head[hv] = imod;
      if (wi <= i) {
        var rem = s - i;
        if ((lc_1 > 7e3 || li > 24576) && (rem > 423 || !lst)) {
          pos = wblk(dat, w, 0, syms, lf, df, eb, li, bs, i - bs, pos);
          li = lc_1 = eb = 0, bs = i;
          for (var j = 0; j < 286; ++j)
            lf[j] = 0;
          for (var j = 0; j < 30; ++j)
            df[j] = 0;
        }
        var l = 2, d = 0, ch_1 = c, dif = imod - pimod & 32767;
        if (rem > 2 && hv == hsh(i - dif)) {
          var maxn = Math.min(n, rem) - 1;
          var maxd = Math.min(32767, i);
          var ml = Math.min(258, rem);
          while (dif <= maxd && --ch_1 && imod != pimod) {
            if (dat[i + l] == dat[i + l - dif]) {
              var nl = 0;
              for (; nl < ml && dat[i + nl] == dat[i + nl - dif]; ++nl)
                ;
              if (nl > l) {
                l = nl, d = dif;
                if (nl > maxn)
                  break;
                var mmd = Math.min(dif, nl - 2);
                var md = 0;
                for (var j = 0; j < mmd; ++j) {
                  var ti = i - dif + j & 32767;
                  var pti = prev[ti];
                  var cd = ti - pti & 32767;
                  if (cd > md)
                    md = cd, pimod = ti;
                }
              }
            }
            imod = pimod, pimod = prev[imod];
            dif += imod - pimod & 32767;
          }
        }
        if (d) {
          syms[li++] = 268435456 | revfl[l] << 18 | revfd[d];
          var lin = revfl[l] & 31, din = revfd[d] & 31;
          eb += fleb[lin] + fdeb[din];
          ++lf[257 + lin];
          ++df[din];
          wi = i + l;
          ++lc_1;
        } else {
          syms[li++] = dat[i];
          ++lf[dat[i]];
        }
      }
    }
    for (i = Math.max(i, wi); i < s; ++i) {
      syms[li++] = dat[i];
      ++lf[dat[i]];
    }
    pos = wblk(dat, w, lst, syms, lf, df, eb, li, bs, i - bs, pos);
    if (!lst) {
      st.r = pos & 7 | w[pos / 8 | 0] << 3;
      pos -= 7;
      st.h = head, st.p = prev, st.i = i, st.w = wi;
    }
  } else {
    for (var i = st.w || 0; i < s + lst; i += 65535) {
      var e = i + 65535;
      if (e >= s) {
        w[pos / 8 | 0] = lst;
        e = s;
      }
      pos = wfblk(w, pos + 1, dat.subarray(i, e));
    }
    st.i = s;
  }
  return slc(o, 0, pre + shft(pos) + post);
};
var crct = /* @__PURE__ */ (function() {
  var t = new Int32Array(256);
  for (var i = 0; i < 256; ++i) {
    var c = i, k = 9;
    while (--k)
      c = (c & 1 && -306674912) ^ c >>> 1;
    t[i] = c;
  }
  return t;
})();
var crc = function() {
  var c = -1;
  return {
    p: function(d) {
      var cr = c;
      for (var i = 0; i < d.length; ++i)
        cr = crct[cr & 255 ^ d[i]] ^ cr >>> 8;
      c = cr;
    },
    d: function() {
      return ~c;
    }
  };
};
var dopt = function(dat, opt, pre, post, st) {
  if (!st) {
    st = { l: 1 };
    if (opt.dictionary) {
      var dict = opt.dictionary.subarray(-32768);
      var newDat = new u8(dict.length + dat.length);
      newDat.set(dict);
      newDat.set(dat, dict.length);
      dat = newDat;
      st.w = dict.length;
    }
  }
  return dflt(dat, opt.level == null ? 6 : opt.level, opt.mem == null ? st.l ? Math.ceil(Math.max(8, Math.min(13, Math.log(dat.length))) * 1.5) : 20 : 12 + opt.mem, pre, post, st);
};
var wbytes = function(d, b, v) {
  for (; v; ++b)
    d[b] = v, v >>>= 8;
};
var gzh = function(c, o) {
  var fn = o.filename;
  c[0] = 31, c[1] = 139, c[2] = 8, c[8] = o.level < 2 ? 4 : o.level == 9 ? 2 : 0, c[9] = 3;
  if (o.mtime != 0)
    wbytes(c, 4, Math.floor(new Date(o.mtime || Date.now()) / 1e3));
  if (fn) {
    c[3] = 8;
    for (var i = 0; i <= fn.length; ++i)
      c[i + 10] = fn.charCodeAt(i);
  }
};
var gzs = function(d) {
  if (d[0] != 31 || d[1] != 139 || d[2] != 8)
    err(6, "invalid gzip data");
  var flg = d[3];
  var st = 10;
  if (flg & 4)
    st += (d[10] | d[11] << 8) + 2;
  for (var zs = (flg >> 3 & 1) + (flg >> 4 & 1); zs > 0; zs -= !d[st++])
    ;
  return st + (flg & 2);
};
var gzl = function(d) {
  var l = d.length;
  return (d[l - 4] | d[l - 3] << 8 | d[l - 2] << 16 | d[l - 1] << 24) >>> 0;
};
var gzhl = function(o) {
  return 10 + (o.filename ? o.filename.length + 1 : 0);
};
function gzipSync(data, opts) {
  if (!opts)
    opts = {};
  var c = crc(), l = data.length;
  c.p(data);
  var d = dopt(data, opts, gzhl(opts), 8), s = d.length;
  return gzh(d, opts), wbytes(d, s - 8, c.d()), wbytes(d, s - 4, l), d;
}
function gunzipSync(data, opts) {
  var st = gzs(data);
  if (st + 8 > data.length)
    err(6, "invalid gzip data");
  return inflt(data.subarray(st, -8), { i: 2 }, opts && opts.out || new u8(gzl(data)), opts && opts.dictionary);
}
var td = typeof TextDecoder != "undefined" && /* @__PURE__ */ new TextDecoder();
var tds = 0;
try {
  td.decode(et, { stream: true });
  tds = 1;
} catch (e) {
}

// src/lib/hachimiTranslator.ts
var RADIX = 1024;
var HEADER_SCALE = 16;
var SALT_RANGE = 64;
var VIBES = {
  error: "\u55B5\uFF01\u4F60\u5728\u72D7\u53EB\u4EC0\u4E48\uFF01\uFF01\uFF01\u{1F63E}\u{1F63E}\u{1F63E}"
};
var BASE_WORDS = dedupeList(
  [
    "\u54C8\u57FA\u7C73",
    "\u5357\u5317\u7EFF\u8C46",
    "\u963F\u897F\u560E",
    "\u54C8\u4E9A\u5E93",
    "\u54C8\u4E9A\u5E93\u7EB3\u54AF",
    "\u66FC\u6CE2",
    "\u66FC\u6CE2\u6CE2\u6CE2",
    "\u54E6\u739B\u5409\u5229",
    "\u5927\u72D7\u53EB",
    "\u6CA1\u6709",
    "\u86CB\u86CB",
    "\u53EE\u549A\u9E21",
    "\u53EE\u53EE\u549A\u549A",
    "\u5976\u9F99",
    "\u54E6\u4E48\u5409\u5229",
    "\u54C8\u5440\u5E93",
    "\u54E6\u8036",
    "\u5185\u4E2A"
  ],
  "BASE_WORDS"
);
var LEAD_BASES = ["\u54C8\u57FA\u7C73", "\u5357\u5317\u7EFF\u8C46", "\u66FC\u6CE2"];
var LEAD_BASE_SET = new Set(LEAD_BASES);
var ONOMATOPOEIA = dedupeList(
  [
    "\u554A",
    "\u54E6",
    "\u5440",
    "\u5475",
    "\u8036",
    "\u55B5",
    "\u8BF6",
    "\u53EB",
    "\u5654",
    "duang",
    "leg",
    "mua",
    "miao"
  ],
  "ONOMATOPOEIA"
);
var SYMBOLS = dedupeList(
  [
    "\u266A",
    "\u266B",
    "\u266C",
    "\u2669",
    "\u266D",
    "\u266E",
    "\u266F",
    "#",
    "\u2197",
    "\u2198",
    "\u2191",
    "\u2193",
    "\u2192",
    "~",
    "~~",
    "\u3002",
    ",",
    "!",
    "?",
    "\u2026",
    "\xB7",
    "\u2605",
    "\u2606",
    "\u2764",
    "\u{1D11E}",
    "\u{1D122}",
    "\u{1D121}"
  ],
  "SYMBOLS"
);
var EMOJIS = dedupeList(
  ["\u{1F408}", "\u{1F63B}", "\u{1F431}", "\u{1F408}\u200D\u2B1B", "\u{1F63A}", "\u{1F638}", "\u{1F639}", "\u{1F63C}", "\u{1F63D}", "\u{1F640}", "\u{1F63F}", "\u{1F63E}"],
  "EMOJIS"
);
var KAOMOJIS = dedupeList(
  [
    "\u2267\u25BD\u2266",
    "\uFF3E\u25BD\uFF3E",
    "\uFFE3\u25BD\uFFE3",
    "\u2022\u203F\u2022",
    "\u25E0\u203F\u25E0",
    "\u2665\u203F\u2665",
    "\xAC\u203F\xAC",
    "\u0298\u203F\u0298",
    "\u2022\u03C9\u2022",
    "\u25D5\u203F\u25D5",
    "\u2267\u25E1\u2266",
    "\uFF65\u03C9\uFF65",
    "\u0295\u2022\u1D25\u2022\u0294"
  ],
  "KAOMOJIS"
);
var BASE_COUNT = BASE_WORDS.length;
var DEFAULT_WEIGHTS = {
  base: 5,
  onomat: 5,
  symbol: 1,
  emoji: 0.5,
  kaomoji: 0.2
};
var textEncoder = new TextEncoder();
var textDecoder = new TextDecoder();
var cryptoSource = globalThis.crypto;
var maybeProcess = globalThis.process;
var debugEnabled = !!maybeProcess?.env?.VITEST;
function debugLog(message, payload) {
  if (debugEnabled) {
    console.debug(`[hachimi] ${message}`, payload);
  }
}
var CONFIG_CACHE = /* @__PURE__ */ new Map();
function getConfig(weights) {
  const resolved = resolveWeights(weights);
  const cacheKey = JSON.stringify([
    resolved.base,
    resolved.onomat,
    resolved.symbol,
    resolved.emoji,
    resolved.kaomoji,
    BASE_WORDS.length,
    ONOMATOPOEIA.length,
    SYMBOLS.length,
    EMOJIS.length,
    KAOMOJIS.length
  ]);
  const cached = CONFIG_CACHE.get(cacheKey);
  if (cached) {
    return cached;
  }
  const built = buildConfig(resolved);
  CONFIG_CACHE.set(cacheKey, built);
  return built;
}
function resolveWeights(weights) {
  const merged = { ...DEFAULT_WEIGHTS, ...weights };
  if (merged.base <= 0) {
    merged.base = DEFAULT_WEIGHTS.base;
  }
  return merged;
}
function buildConfig(weights) {
  const combosPerBase = Math.ceil(RADIX / BASE_COUNT);
  const templates = Array.from(
    { length: combosPerBase },
    () => ({})
  );
  const ratio = (value) => {
    if (value <= 0 || weights.base <= 0) {
      return 0;
    }
    return Math.min(1, value / weights.base);
  };
  const targetCounts = {
    onomat: Math.min(
      combosPerBase,
      Math.round(combosPerBase * ratio(weights.onomat))
    ),
    symbol: Math.min(
      combosPerBase,
      Math.round(combosPerBase * ratio(weights.symbol))
    ),
    emoji: Math.min(
      combosPerBase,
      Math.round(combosPerBase * ratio(weights.emoji))
    ),
    kaomoji: Math.min(
      combosPerBase,
      Math.round(combosPerBase * ratio(weights.kaomoji))
    )
  };
  distributeCategory(
    "onomatSeed",
    targetCounts.onomat,
    ONOMATOPOEIA.length,
    templates
  );
  distributeCategory(
    "symbolSeed",
    targetCounts.symbol,
    SYMBOLS.length,
    templates
  );
  distributeCategory("emojiSeed", targetCounts.emoji, EMOJIS.length, templates);
  distributeCategory(
    "kaomojiSeed",
    targetCounts.kaomoji,
    KAOMOJIS.length,
    templates
  );
  ensureUniqueTemplates(templates);
  return { weights, combosPerBase, variantTemplates: templates };
}
function templateSignature(template) {
  return [
    template.onomatSeed ?? "x",
    template.symbolSeed ?? "x",
    template.emojiSeed ?? "x",
    template.kaomojiSeed ?? "x"
  ].join("|");
}
function ensureUniqueTemplates(templates) {
  const used = /* @__PURE__ */ new Set();
  templates.forEach((template, index) => {
    let signature = templateSignature(template);
    if (used.has(signature)) {
      signature = forceUniqueTemplate(template, index, used);
    }
    used.add(signature);
  });
}
function forceUniqueTemplate(template, variantIndex, used) {
  const baseCandidates = [
    { key: "emojiSeed", pool: EMOJIS.length },
    { key: "symbolSeed", pool: SYMBOLS.length },
    { key: "kaomojiSeed", pool: KAOMOJIS.length },
    { key: "onomatSeed", pool: ONOMATOPOEIA.length }
  ];
  const candidates = baseCandidates.filter((entry) => entry.pool > 0);
  if (candidates.length === 0) {
    throw new Error("no-category-to-break-collision");
  }
  const prioritized = [
    ...candidates.filter((entry) => template[entry.key] === void 0),
    ...candidates.filter((entry) => template[entry.key] !== void 0)
  ];
  for (const candidate of prioritized) {
    const original = template[candidate.key];
    const baseSeed = (original ?? variantIndex) % candidate.pool;
    for (let step = 0; step < candidate.pool; step += 1) {
      const updated = (baseSeed + step) % candidate.pool;
      template[candidate.key] = updated;
      const signature = templateSignature(template);
      if (!used.has(signature)) {
        return signature;
      }
    }
    if (original === void 0) {
      template[candidate.key] = void 0;
    } else {
      template[candidate.key] = original;
    }
  }
  throw new Error("unable-to-deduplicate-variants");
}
function distributeCategory(key, count, poolLength, templates) {
  if (count <= 0 || poolLength === 0) {
    return;
  }
  const step = templates.length / count;
  let cursor = 0;
  for (let assigned = 0; assigned < count; assigned += 1) {
    const preferred = Math.min(templates.length - 1, Math.floor(cursor));
    const slot = findAvailableTemplate(templates, preferred, key);
    templates[slot][key] = assigned % poolLength;
    cursor += step;
  }
}
function findAvailableTemplate(templates, start, key) {
  const length = templates.length;
  for (let offset = 0; offset < length; offset += 1) {
    const index = (start + offset) % length;
    if (templates[index][key] === void 0) {
      return index;
    }
  }
  return start % length;
}
function randomIndex(limit) {
  if (limit <= 1) return 0;
  if (cryptoSource?.getRandomValues) {
    const bucket = new Uint32Array(1);
    cryptoSource.getRandomValues(bucket);
    return bucket[0] % limit;
  }
  return Math.floor(Math.random() * limit);
}
var BASE_MATCHER = buildMatcher(BASE_WORDS);
var ONO_MATCHER = buildMatcher(ONOMATOPOEIA);
var SYMBOL_MATCHER = buildMatcher(SYMBOLS);
var EMOJI_MATCHER = buildMatcher(EMOJIS);
var KAO_MATCHER = buildMatcher(KAOMOJIS);
function encodeHuman(text, config) {
  const inputLength = text.length;
  if (!text.trim()) {
    return {
      ok: true,
      output: "",
      stats: {
        plainBytes: 0,
        payloadBytes: 0,
        tokenCount: 0,
        inputLength,
        outputLength: 0
      }
    };
  }
  try {
    const payload = packPayload(text);
    const compressed = gzipSync(payload, { mtime: 0, level: 9 });
    const { chunks, tailBits } = chunkify(compressed);
    const salt = randomIndex(SALT_RANGE);
    const headerValue = tailBits + HEADER_SCALE * salt;
    const encodedTokens = [];
    encodedTokens.push(valueToToken(headerValue, config));
    chunks.forEach((chunk) => {
      const shifted = (chunk + salt) % RADIX;
      encodedTokens.push(valueToToken(shifted, config));
    });
    const leadToken = LEAD_BASES[randomIndex(LEAD_BASES.length)];
    const output = leadToken + encodedTokens.join("");
    return {
      ok: true,
      output,
      stats: {
        plainBytes: payload.length - 4,
        payloadBytes: compressed.length,
        tokenCount: chunks.length,
        inputLength,
        outputLength: output.length
      }
    };
  } catch (error) {
    console.error("Hachimi encode failed", error);
    return { ok: false, output: "", error: VIBES.error };
  }
}
function decodeHachimi(text, config) {
  const compact = text.replace(/\s+/g, "");
  const inputLength = text.length;
  if (!compact) {
    return {
      ok: true,
      output: "",
      stats: {
        plainBytes: 0,
        payloadBytes: 0,
        tokenCount: 0,
        inputLength,
        outputLength: 0
      }
    };
  }
  try {
    const parsedTokens = parseTokens(compact);
    if (!parsedTokens || parsedTokens.length < 2) {
      debugLog("decode-parse-failed", {
        compact,
        parsed: parsedTokens?.length ?? 0
      });
      return { ok: false, output: "", error: VIBES.error };
    }
    const [leadToken, ...payloadTokens] = parsedTokens;
    const leadWord = BASE_WORDS[leadToken.baseIndex];
    if (!LEAD_BASE_SET.has(leadWord)) {
      return { ok: false, output: "", error: VIBES.error };
    }
    const headerValue = tokenPartsToValue(payloadTokens[0], config);
    if (headerValue === null) {
      debugLog("decode-header-token-mismatch", { token: payloadTokens[0] });
      return { ok: false, output: "", error: VIBES.error };
    }
    const salt = Math.floor(headerValue / HEADER_SCALE);
    const tailBits = headerValue % HEADER_SCALE;
    if (salt >= SALT_RANGE || tailBits >= 10) {
      debugLog("decode-header-out-of-range", { salt, tailBits });
      return { ok: false, output: "", error: VIBES.error };
    }
    const chunkValues = [];
    payloadTokens.slice(1).forEach((token, index) => {
      const effectiveValue = tokenPartsToValue(token, config);
      if (effectiveValue === null) {
        debugLog("decode-payload-token-mismatch", { token, index });
        throw new Error("invalid-token");
      }
      const original = (effectiveValue - salt + RADIX) % RADIX;
      chunkValues.push(original);
    });
    if (chunkValues.length === 0) {
      debugLog("decode-empty-chunks");
      return { ok: false, output: "", error: VIBES.error };
    }
    const compressed = unchunkify(chunkValues, tailBits);
    let restoredPayload;
    try {
      restoredPayload = gunzipSync(compressed);
    } catch (gunzipError) {
      debugLog("decode-gzip-failed", { chunkValues, tailBits, headerValue });
      throw gunzipError;
    }
    const restored = unpackPayload(restoredPayload);
    if (!selfCheck(restored, chunkValues, tailBits)) {
      debugLog("decode-self-check-failed", {
        restored,
        chunkValues,
        tailBits,
        reencoded: chunkify(
          gzipSync(packPayload(restored), { mtime: 0, level: 9 })
        ).chunks
      });
      return { ok: false, output: "", error: VIBES.error };
    }
    return {
      ok: true,
      output: restored,
      stats: {
        plainBytes: textEncoder.encode(restored).length,
        payloadBytes: compressed.length,
        tokenCount: chunkValues.length,
        inputLength,
        outputLength: restored.length
      }
    };
  } catch (error) {
    debugLog("decode-exception", error);
    return { ok: false, output: "", error: VIBES.error };
  }
}
function translate(text, role, options) {
  const config = getConfig(options?.weights);
  return role === "human" ? encodeHuman(text, config) : decodeHachimi(text, config);
}
function selfCheck(message, observedChunks, observedTail) {
  try {
    const payload = packPayload(message);
    const compressed = gzipSync(payload, { mtime: 0, level: 9 });
    const next = chunkify(compressed);
    if (next.tailBits !== observedTail) {
      return false;
    }
    if (next.chunks.length !== observedChunks.length) {
      return false;
    }
    for (let i = 0; i < next.chunks.length; i += 1) {
      if (next.chunks[i] !== observedChunks[i]) {
        return false;
      }
    }
    return true;
  } catch (error) {
    console.error("Hachimi self-check failed", error);
    return false;
  }
}
function chunkify(bytes) {
  let buffer = 0;
  let bitCount = 0;
  const chunks = [];
  bytes.forEach((byte) => {
    buffer = buffer << 8 | byte;
    bitCount += 8;
    while (bitCount >= 10) {
      bitCount -= 10;
      const chunk = buffer >> bitCount & 1023;
      chunks.push(chunk);
      buffer &= (1 << bitCount) - 1;
    }
  });
  const tailBits = bitCount;
  if (bitCount > 0) {
    const chunk = buffer << 10 - bitCount & 1023;
    chunks.push(chunk);
  }
  return { chunks, tailBits };
}
function unchunkify(chunks, tailBits) {
  if (chunks.length === 0) {
    return new Uint8Array();
  }
  const bytes = [];
  let buffer = 0;
  let bitCount = 0;
  chunks.forEach((chunk, index) => {
    let value = chunk;
    let bits2 = 10;
    if (index === chunks.length - 1 && tailBits > 0 && tailBits < 10) {
      value >>= 10 - tailBits;
      bits2 = tailBits;
    }
    buffer = buffer << bits2 | value;
    bitCount += bits2;
    while (bitCount >= 8) {
      bitCount -= 8;
      const byte = buffer >> bitCount & 255;
      bytes.push(byte);
      buffer &= (1 << bitCount) - 1;
    }
  });
  if (bitCount !== 0) {
    throw new Error("dangling-bits");
  }
  return new Uint8Array(bytes);
}
function buildMatcher(pool) {
  return pool.map((token, index) => ({ token, index })).sort((a, b) => b.token.length - a.token.length);
}
var CATEGORY_SEQUENCE = [
  { matcher: ONO_MATCHER, assign: "onomatIdx" },
  { matcher: EMOJI_MATCHER, assign: "emojiIdx" },
  { matcher: SYMBOL_MATCHER, assign: "symbolIdx" },
  { matcher: KAO_MATCHER, assign: "kaomojiIdx" }
];
function parseTokens(text) {
  const memo = /* @__PURE__ */ new Map();
  function dfs(index) {
    if (index === text.length) {
      return [];
    }
    if (memo.has(index)) {
      return memo.get(index) ?? null;
    }
    const options = collectTokenOptions(text, index);
    for (const option of options) {
      const continuation = dfs(option.end);
      if (continuation) {
        const result = [option, ...continuation];
        memo.set(index, result);
        return result;
      }
    }
    memo.set(index, null);
    return null;
  }
  return dfs(0);
}
function collectTokenOptions(text, start) {
  const baseMatch = matchAt(BASE_MATCHER, text, start);
  if (!baseMatch) {
    debugLog("parse-base-miss", { start, peek: text.slice(start, start + 12) });
    return [];
  }
  const resolvedBaseMatch = baseMatch;
  const results = [];
  function walk(categoryIndex, cursor, parts) {
    if (categoryIndex === CATEGORY_SEQUENCE.length) {
      results.push({
        baseIndex: resolvedBaseMatch.index,
        parts: { ...parts },
        end: cursor
      });
      return;
    }
    const descriptor = CATEGORY_SEQUENCE[categoryIndex];
    const match = matchAt(descriptor.matcher, text, cursor);
    if (match) {
      const nextParts = {
        ...parts,
        [descriptor.assign]: match.index
      };
      walk(categoryIndex + 1, cursor + match.token.length, nextParts);
    }
    walk(categoryIndex + 1, cursor, parts);
  }
  walk(0, start + resolvedBaseMatch.token.length, {});
  return results;
}
function matchAt(matcher, text, start) {
  for (const entry of matcher) {
    if (text.startsWith(entry.token, start)) {
      return entry;
    }
  }
  return null;
}
function tokenPartsToValue(token, config) {
  const variantIndex = locateVariantIndex(token.baseIndex, token.parts, config);
  if (variantIndex < 0) {
    return null;
  }
  const value = variantIndex * BASE_COUNT + token.baseIndex;
  if (value >= RADIX) {
    return null;
  }
  return value;
}
function valueToToken(value, config) {
  if (value < 0 || value >= RADIX) {
    throw new Error("value-out-of-range");
  }
  const variantIndex = Math.floor(value / BASE_COUNT);
  const baseIndex = value % BASE_COUNT;
  if (variantIndex >= config.variantTemplates.length) {
    throw new Error("variant-overflow");
  }
  const parts = materializeParts(
    config.variantTemplates[variantIndex],
    baseIndex
  );
  return composeToken(baseIndex, parts);
}
function composeToken(baseIndex, parts) {
  let token = BASE_WORDS[baseIndex];
  if (parts.onomatIdx !== void 0) {
    token += ONOMATOPOEIA[parts.onomatIdx];
  }
  if (parts.emojiIdx !== void 0) {
    token += EMOJIS[parts.emojiIdx];
  }
  if (parts.symbolIdx !== void 0) {
    token += SYMBOLS[parts.symbolIdx];
  }
  if (parts.kaomojiIdx !== void 0) {
    token += KAOMOJIS[parts.kaomojiIdx];
  }
  return token;
}
function materializeParts(template, baseIndex) {
  const parts = {};
  if (template.onomatSeed !== void 0 && ONOMATOPOEIA.length > 0) {
    parts.onomatIdx = (template.onomatSeed + baseIndex) % ONOMATOPOEIA.length;
  }
  if (template.symbolSeed !== void 0 && SYMBOLS.length > 0) {
    parts.symbolIdx = (template.symbolSeed + baseIndex) % SYMBOLS.length;
  }
  if (template.emojiSeed !== void 0 && EMOJIS.length > 0) {
    parts.emojiIdx = (template.emojiSeed + baseIndex) % EMOJIS.length;
  }
  if (template.kaomojiSeed !== void 0 && KAOMOJIS.length > 0) {
    parts.kaomojiIdx = (template.kaomojiSeed + baseIndex) % KAOMOJIS.length;
  }
  return parts;
}
function locateVariantIndex(baseIndex, parts, config) {
  for (let i = 0; i < config.variantTemplates.length; i += 1) {
    if (matchesTemplate(config.variantTemplates[i], baseIndex, parts)) {
      return i;
    }
  }
  return -1;
}
function matchesTemplate(template, baseIndex, parts) {
  if (!matchCategory(
    template.onomatSeed,
    ONOMATOPOEIA.length,
    baseIndex,
    parts.onomatIdx
  )) {
    return false;
  }
  if (!matchCategory(
    template.symbolSeed,
    SYMBOLS.length,
    baseIndex,
    parts.symbolIdx
  )) {
    return false;
  }
  if (!matchCategory(template.emojiSeed, EMOJIS.length, baseIndex, parts.emojiIdx)) {
    return false;
  }
  if (!matchCategory(
    template.kaomojiSeed,
    KAOMOJIS.length,
    baseIndex,
    parts.kaomojiIdx
  )) {
    return false;
  }
  return true;
}
function matchCategory(seed, poolLength, baseIndex, observed) {
  if (seed === void 0 || poolLength === 0) {
    return observed === void 0;
  }
  if (observed === void 0) {
    return false;
  }
  const expected = (seed + baseIndex) % poolLength;
  return expected === observed;
}
function dedupeList(values, label) {
  const seen = /* @__PURE__ */ new Set();
  const unique = [];
  values.forEach((value) => {
    if (!seen.has(value)) {
      seen.add(value);
      unique.push(value);
    } else {
      console.warn(`[hachimi] removed duplicate entry "${value}" from ${label}`);
    }
  });
  return unique;
}
function fnv1a(bytes) {
  let hash = 2166136261;
  for (const byte of bytes) {
    hash ^= byte;
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}
function numberToBytes(value) {
  const buffer = new ArrayBuffer(4);
  new DataView(buffer).setUint32(0, value, false);
  return new Uint8Array(buffer);
}
function bytesToNumber(bytes) {
  if (bytes.length !== 4) return 0;
  return new DataView(
    bytes.buffer,
    bytes.byteOffset,
    bytes.byteLength
  ).getUint32(0, false);
}
function packPayload(text) {
  const body = textEncoder.encode(text);
  const checksum = numberToBytes(fnv1a(body));
  const payload = new Uint8Array(body.length + checksum.length);
  payload.set(body, 0);
  payload.set(checksum, body.length);
  return payload;
}
function unpackPayload(payload) {
  if (payload.length < 4) {
    throw new Error("payload-too-short");
  }
  const body = payload.subarray(0, payload.length - 4);
  const storedChecksum = payload.subarray(payload.length - 4);
  const computed = fnv1a(body);
  if (computed !== bytesToNumber(storedChecksum)) {
    throw new Error("checksum-mismatch");
  }
  return textDecoder.decode(body);
}
export {
  translate
};
