//! Optional native seams for Moneta, admitted under the v5/v6 seam rule.
//!
//! Seam 1 — the cosine scan behind `moneta.vector_index.VectorIndex.query`.
//!
//! The seam rule admits Rust only behind a pure seam with an exact oracle,
//! where it buys speed or a guarantee (owner confirmation pending: O27).
//! D1's latency gate did not fire (numpy clears it); the guarantee here is
//! bit-exact parity, which numpy cannot give. The oracle
//! here is the pure-Python scan in `vector_index.py`; the conformance suite
//! (`tests/unit/test_native_scan_conformance.py`) requires bit-identical
//! cosines and identical ordering, ties included.
//!
//! How exactness is kept:
//!   * every sum is a sequential left fold in the same element order as the
//!     Python loop (`dot += a * b`, `norm += a * a`), in f64;
//!   * rustc never reassociates or FMA-contracts f64 arithmetic without
//!     explicit fast-math intrinsics, and none are used;
//!   * `sqrt` and `/` are correctly rounded IEEE-754 on both sides;
//!   * a row's squared norm is cached at upsert, computed by the same fold
//!     the oracle recomputes per query, so the cached value is identical;
//!   * order is cosine descending, then row ascending. Rows are assigned in
//!     dict insertion order by the Python facade, so this equals Python's
//!     stable `sort(reverse=True)` over the dict.

use pyo3::exceptions::{PyArithmeticError, PyIndexError, PyValueError};
use pyo3::prelude::*;
use std::cmp::Ordering;

/// Sequential left-fold dot product, matching the Python oracle's loop.
#[inline]
fn dot_seq(a: &[f64], b: &[f64]) -> f64 {
    let mut acc = 0.0_f64;
    for i in 0..a.len() {
        acc += a[i] * b[i];
    }
    acc
}


/// CPython's `sum()` over floats, reproduced per interpreter.
///
/// * CPython <= 3.11 adds left to right: `f += x`.
/// * CPython >= 3.12 uses Neumaier's compensated sum, then adds the
///   compensation once at the end if it is nonzero and finite
///   (Python/bltinmodule.c, `builtin_sum_impl`).
///
/// The int start value `0` behaves exactly like `0.0` for these inputs
/// (`0 + -0.0 == 0.0` in both), so both modes start from `0.0`.
#[inline]
pub fn py_sum(values: impl Iterator<Item = f64>, compensated: bool) -> f64 {
    let mut f = 0.0_f64;
    if !compensated {
        for x in values {
            f += x;
        }
        return f;
    }
    let mut c = 0.0_f64;
    for x in values {
        let t = f + x;
        if f.abs() >= x.abs() {
            c += (f - t) + x;
        } else {
            c += (x - t) + f;
        }
        f = t;
    }
    if c != 0.0 && c.is_finite() {
        f += c;
    }
    f
}

/// Raised when a cosine would be NaN. The oracle's ordering of NaN keys is
/// an artifact of CPython's sort, not something a total order can match, so
/// the facade answers such queries with the oracle itself.
#[derive(Debug, PartialEq)]
pub struct NonExact;

/// Pure kernel: cosine of `query` against every live row with nonzero norm.
/// Returns `(row, cos)` for the top `k`, cosine descending then row ascending,
/// or `NonExact` if any cosine is NaN (finite inputs can still overflow:
/// components near 1e308 make a norm or dot infinite).
pub fn scan_topk(
    data: &[f64],
    norm_sq: &[f64],
    alive: &[bool],
    dim: usize,
    query: &[f64],
    k: usize,
) -> Result<Vec<(usize, f64)>, NonExact> {
    if k == 0 || dim == 0 || query.len() != dim {
        return Ok(Vec::new());
    }
    let q_norm_sq = dot_seq(query, query);
    if q_norm_sq == 0.0 {
        return Ok(Vec::new());
    }
    let q_norm = q_norm_sq.sqrt();
    let mut scored: Vec<(usize, f64)> = Vec::with_capacity(norm_sq.len());
    for (row, &nsq) in norm_sq.iter().enumerate() {
        if !alive[row] || nsq == 0.0 {
            continue;
        }
        let v = &data[row * dim..(row + 1) * dim];
        // The oracle computes dot as sum(vec[i] * query[i]).
        let dot = dot_seq(v, query);
        let cos = dot / (nsq.sqrt() * q_norm);
        if cos.is_nan() {
            return Err(NonExact);
        }
        scored.push((row, cos));
    }
    // With NaN excluded this is a total order: cos desc (-0.0 == 0.0, as in
    // Python), then row asc. Rows are unique, so no two keys compare Equal.
    let cmp = |a: &(usize, f64), b: &(usize, f64)| -> Ordering {
        match b.1.partial_cmp(&a.1) {
            Some(Ordering::Equal) => a.0.cmp(&b.0),
            Some(o) => o,
            None => unreachable!("NaN excluded above"),
        }
    };
    if k < scored.len() {
        scored.select_nth_unstable_by(k - 1, cmp);
        scored.truncate(k);
    }
    scored.sort_unstable_by(cmp);
    Ok(scored)
}

/// Contiguous f64 row store with cached squared norms.
///
/// Rows are append-only slots; `kill` tombstones a slot and `compact`
/// rewrites live slots in their existing order. The Python facade owns the
/// id <-> row mapping and the entity state.
#[pyclass(module = "moneta_native")]
pub struct ScanIndex {
    dim: usize,
    data: Vec<f64>,
    norm_sq: Vec<f64>,
    alive: Vec<bool>,
    live: usize,
}

impl ScanIndex {
    fn check(&self, vec: &[f64]) -> PyResult<()> {
        if vec.len() != self.dim {
            return Err(PyValueError::new_err(format!(
                "embedding dim mismatch: expected {}, got {}",
                self.dim,
                vec.len()
            )));
        }
        if vec.iter().any(|x| !x.is_finite()) {
            return Err(PyValueError::new_err("embedding contains non-finite values"));
        }
        Ok(())
    }

    fn check_row(&self, row: usize) -> PyResult<()> {
        if row >= self.alive.len() || !self.alive[row] {
            return Err(PyIndexError::new_err(format!("no live row {row}")));
        }
        Ok(())
    }
}

#[pymethods]
impl ScanIndex {
    #[new]
    fn new(dim: usize) -> PyResult<Self> {
        if dim == 0 {
            return Err(PyValueError::new_err("dim must be positive"));
        }
        Ok(Self { dim, data: Vec::new(), norm_sq: Vec::new(), alive: Vec::new(), live: 0 })
    }

    #[getter]
    fn dim(&self) -> usize {
        self.dim
    }

    /// Number of slots, live or dead.
    fn slots(&self) -> usize {
        self.alive.len()
    }

    fn __len__(&self) -> usize {
        self.live
    }

    /// Append a row; returns its slot.
    fn push(&mut self, vec: Vec<f64>) -> PyResult<usize> {
        self.check(&vec)?;
        let nsq = dot_seq(&vec, &vec);
        self.data.extend_from_slice(&vec);
        self.norm_sq.push(nsq);
        self.alive.push(true);
        self.live += 1;
        Ok(self.alive.len() - 1)
    }

    /// Overwrite a live row in place (an upsert of an existing id keeps its
    /// position, like a dict assignment).
    fn set(&mut self, row: usize, vec: Vec<f64>) -> PyResult<()> {
        self.check_row(row)?;
        self.check(&vec)?;
        self.norm_sq[row] = dot_seq(&vec, &vec);
        self.data[row * self.dim..(row + 1) * self.dim].copy_from_slice(&vec);
        Ok(())
    }

    fn get(&self, row: usize) -> PyResult<Vec<f64>> {
        self.check_row(row)?;
        Ok(self.data[row * self.dim..(row + 1) * self.dim].to_vec())
    }

    /// Tombstone a row. Idempotent on dead rows.
    fn kill(&mut self, row: usize) -> PyResult<()> {
        if row >= self.alive.len() {
            return Err(PyIndexError::new_err(format!("no row {row}")));
        }
        if self.alive[row] {
            self.alive[row] = false;
            self.live -= 1;
        }
        Ok(())
    }

    /// Drop dead slots, keeping live rows in order. Returns old->new slot
    /// (-1 for dead rows).
    fn compact(&mut self) -> Vec<i64> {
        let mut mapping = Vec::with_capacity(self.alive.len());
        let mut w = 0usize;
        for r in 0..self.alive.len() {
            if self.alive[r] {
                if w != r {
                    self.data.copy_within(r * self.dim..(r + 1) * self.dim, w * self.dim);
                    self.norm_sq[w] = self.norm_sq[r];
                }
                mapping.push(w as i64);
                w += 1;
            } else {
                mapping.push(-1);
            }
        }
        self.data.truncate(w * self.dim);
        self.norm_sq.truncate(w);
        self.alive.clear();
        self.alive.resize(w, true);
        self.live = w;
        mapping
    }

    /// Top-k `(slot, cosine)`; cosine descending, slot ascending.
    /// Raises `ArithmeticError` when a cosine would be NaN; the caller must
    /// then answer with the Python oracle.
    fn scan(&self, query: Vec<f64>, k: usize) -> PyResult<Vec<(usize, f64)>> {
        if query.len() != self.dim {
            return Ok(Vec::new());
        }
        scan_topk(&self.data, &self.norm_sq, &self.alive, self.dim, &query, k).map_err(|_| {
            PyArithmeticError::new_err("NaN cosine (overflow or non-finite input): use the oracle")
        })
    }

    /// v5 seam (`moneta.v5.index.ExactIndex.cosines`): for each slot, the
    /// dot of its stored unit vector with the already-normalized query `q`,
    /// summed exactly as the running interpreter's `sum()` would
    /// (`compensated` = CPython >= 3.12). Returns cosines in `slots` order.
    fn dots(&self, q: Vec<f64>, slots: Vec<usize>, compensated: bool) -> PyResult<Vec<f64>> {
        if q.len() != self.dim {
            return Err(PyValueError::new_err("dots: query dim mismatch"));
        }
        let mut out = Vec::with_capacity(slots.len());
        for &row in &slots {
            self.check_row(row)?;
            let v = &self.data[row * self.dim..(row + 1) * self.dim];
            out.push(py_sum(v.iter().zip(q.iter()).map(|(a, b)| a * b), compensated));
        }
        Ok(out)
    }

    /// Bytes held by the vector store (for memory accounting).
    fn nbytes(&self) -> usize {
        self.data.capacity() * 8 + self.norm_sq.capacity() * 8 + self.alive.capacity()
    }
}


/// Pure kernel: ARCHITECTURE.md §4 lazy decay over a column.
///
/// Mirrors `moneta.decay.decay_value` operation for operation:
/// `dt = now - last; if dt < 0 { dt = 0 }; d = u * exp((-lam) * dt);
/// if d > floor { d } else { floor }`. `f64::exp` lowers to the platform C
/// runtime's `exp`, the same function CPython's `math.exp` calls, which is
/// what the parity test (`test_native_decay_parity.py`) checks bit for bit.
pub fn decay_column(utility: &mut [f64], last: &[f64], floor: &[f64], lam: f64, now: f64) {
    let neg_lam = -lam;
    for i in 0..utility.len() {
        let mut dt = now - last[i];
        if dt < 0.0 {
            dt = 0.0;
        }
        let decayed = utility[i] * (neg_lam * dt).exp();
        utility[i] = if decayed > floor[i] { decayed } else { floor[i] };
    }
}

/// Python entry point for `decay_column`; returns the new utility column.
#[pyfunction]
fn decay_batch(
    mut utility: Vec<f64>,
    last_evaluated: Vec<f64>,
    protected_floor: Vec<f64>,
    lam: f64,
    now: f64,
) -> PyResult<Vec<f64>> {
    if utility.len() != last_evaluated.len() || utility.len() != protected_floor.len() {
        return Err(PyValueError::new_err("decay_batch: column lengths differ"));
    }
    decay_column(&mut utility, &last_evaluated, &protected_floor, lam, now);
    Ok(utility)
}

/// `py_sum` exposed for the parity test against the interpreter's `sum()`.
#[pyfunction]
fn py_sum_list(values: Vec<f64>, compensated: bool) -> f64 {
    py_sum(values.into_iter(), compensated)
}

#[pymodule]
fn moneta_native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<ScanIndex>()?;
    m.add_function(wrap_pyfunction!(decay_batch, m)?)?;
    m.add_function(wrap_pyfunction!(py_sum_list, m)?)?;
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ties_break_by_row() {
        let data = vec![1.0, 0.0, 1.0, 0.0, 0.0, 1.0];
        let nsq = vec![1.0, 1.0, 1.0];
        let alive = vec![true, true, true];
        let r = scan_topk(&data, &nsq, &alive, 2, &[1.0, 0.0], 3).unwrap();
        assert_eq!(r.iter().map(|x| x.0).collect::<Vec<_>>(), vec![0, 1, 2]);
    }

    #[test]
    fn dead_and_zero_rows_skipped() {
        let data = vec![1.0, 0.0, 0.0, 0.0, 1.0, 0.0];
        let nsq = vec![1.0, 0.0, 1.0];
        let alive = vec![false, true, true];
        let r = scan_topk(&data, &nsq, &alive, 2, &[1.0, 0.0], 5).unwrap();
        assert_eq!(r, vec![(2, 1.0)]);
    }

    #[test]
    fn overflow_to_nan_is_reported_not_sorted() {
        // 1e308 is finite, but its squared norm overflows: inf / inf = NaN.
        let v = [1e308, 1e308];
        let data = v.to_vec();
        let nsq = vec![dot_seq(&v, &v)];
        assert!(nsq[0].is_infinite());
        let r = scan_topk(&data, &nsq, &[true], 2, &[1e308, 1e308], 1);
        assert_eq!(r, Err(NonExact));
    }

    #[test]
    fn compensated_sum_recovers_cancellation() {
        // 1e16 + 1 - 1e16: sequential loses the 1, Neumaier keeps it.
        let xs = [1e16, 1.0, -1e16];
        assert_eq!(py_sum(xs.iter().copied(), false), 0.0);
        assert_eq!(py_sum(xs.iter().copied(), true), 1.0);
    }

    #[test]
    fn topk_equals_full_sort_prefix() {
        let dim = 3;
        let mut data = Vec::new();
        let mut nsq = Vec::new();
        for i in 0..50 {
            let v = [((i * 7) % 5) as f64, ((i * 3) % 4) as f64 - 1.5, 1.0];
            nsq.push(dot_seq(&v, &v));
            data.extend_from_slice(&v);
        }
        let alive = vec![true; 50];
        let q = [0.3, -0.2, 0.9];
        let full = scan_topk(&data, &nsq, &alive, dim, &q, 50).unwrap();
        for k in 1..50 {
            assert_eq!(scan_topk(&data, &nsq, &alive, dim, &q, k).unwrap(), full[..k].to_vec());
        }
    }
}
