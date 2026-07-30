"""Vectorized quaternion and transform math for FBX animation ingestion.

Conventions match the rest of the FBX pipeline: ``float64`` throughout and
w-first ``(w, x, y, z)`` quaternions. Every function is vectorized over leading
dimensions so whole animations can be processed without Python loops.

This module must stay free of ``bpy``/``mathutils`` so it can be unit tested
without Blender.
"""

import numpy as np


_EPSILON = 1e-12


def quat_normalize(q: np.ndarray) -> np.ndarray:
    """Normalize quaternions to unit length.

    Args:
        q: Quaternions with shape ``(..., 4)``.

    Returns:
        Unit quaternions with the same shape. Zero-length inputs become identity.
    """
    q = np.asarray(q, dtype=np.float64)
    norm = np.linalg.norm(q, axis=-1, keepdims=True)
    out = np.where(norm > _EPSILON, q / np.maximum(norm, _EPSILON), 0.0)
    out[..., 0] = np.where(norm[..., 0] > _EPSILON, out[..., 0], 1.0)
    return out


def quat_conjugate(q: np.ndarray) -> np.ndarray:
    """Return the conjugate, which is the inverse for unit quaternions.

    Args:
        q: Quaternions with shape ``(..., 4)``.

    Returns:
        Conjugated quaternions with the same shape.
    """
    q = np.asarray(q, dtype=np.float64)
    out = q.copy()
    out[..., 1:] = -out[..., 1:]
    return out


def quat_multiply(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Compose two rotations, applying ``b`` first and then ``a``.

    Args:
        a: Quaternions broadcastable to ``(..., 4)``.
        b: Quaternions broadcastable to ``(..., 4)``.

    Returns:
        The product ``a ∘ b``.
    """
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    aw, ax, ay, az = a[..., 0], a[..., 1], a[..., 2], a[..., 3]
    bw, bx, by, bz = b[..., 0], b[..., 1], b[..., 2], b[..., 3]
    return np.stack(
        [
            aw * bw - ax * bx - ay * by - az * bz,
            aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
        ],
        axis=-1,
    )


def quat_rotate_vector(q: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Rotate vectors by unit quaternions (``v' = q v q*``).

    Args:
        q: Unit quaternions broadcastable to ``(..., 4)``.
        v: Vectors broadcastable to ``(..., 3)``.

    Returns:
        Rotated vectors with shape ``(..., 3)``.
    """
    q = np.asarray(q, dtype=np.float64)
    v = np.asarray(v, dtype=np.float64)
    qw = q[..., 0:1]
    qv = q[..., 1:]
    uv = np.cross(qv, v)
    uuv = np.cross(qv, uv)
    return v + 2.0 * (qw * uv + uuv)


def quat_from_matrix(m: np.ndarray) -> np.ndarray:
    """Convert 3x3 rotation matrices to unit quaternions.

    Uses Shepperd's method, branching on the largest diagonal component for
    numerical stability, vectorized over leading dimensions.

    Args:
        m: Rotation matrices with shape ``(..., 3, 3)``.

    Returns:
        Unit quaternions with shape ``(..., 4)``.
    """
    m = np.asarray(m, dtype=np.float64)
    m00, m01, m02 = m[..., 0, 0], m[..., 0, 1], m[..., 0, 2]
    m10, m11, m12 = m[..., 1, 0], m[..., 1, 1], m[..., 1, 2]
    m20, m21, m22 = m[..., 2, 0], m[..., 2, 1], m[..., 2, 2]

    trace = m00 + m11 + m22

    q_w = np.stack([1.0 + trace, m21 - m12, m02 - m20, m10 - m01], axis=-1)
    q_x = np.stack([m21 - m12, 1.0 + m00 - m11 - m22, m01 + m10, m02 + m20], axis=-1)
    q_y = np.stack([m02 - m20, m01 + m10, 1.0 - m00 + m11 - m22, m12 + m21], axis=-1)
    q_z = np.stack([m10 - m01, m02 + m20, m12 + m21, 1.0 - m00 - m11 + m22], axis=-1)

    choice = np.argmax(np.stack([trace, m00, m11, m22], axis=-1), axis=-1)
    trace_positive = trace > 0.0

    q = np.where(
        trace_positive[..., None],
        q_w,
        np.where(
            (choice == 1)[..., None],
            q_x,
            np.where((choice == 2)[..., None], q_y, q_z),
        ),
    )
    return quat_normalize(q)


def quat_to_euler(q: np.ndarray, order: str = "XYZ") -> np.ndarray:
    """Convert unit quaternions to intrinsic Euler angles in radians.

    Only the rotation orders Blender pose bones can use are supported. The
    result matches ``mathutils.Quaternion.to_euler(order)``.

    Args:
        q: Unit quaternions with shape ``(..., 4)``.
        order: One of ``"XYZ"``, ``"XZY"``, ``"YXZ"``, ``"YZX"``, ``"ZXY"``, ``"ZYX"``.

    Returns:
        Euler angles with shape ``(..., 3)``, always ordered ``(x, y, z)``
        regardless of ``order``.

    Raises:
        ValueError: If ``order`` is not a supported rotation order.
    """
    matrix = quat_to_matrix(q)
    return matrix_to_euler(matrix, order)


def quat_to_matrix(q: np.ndarray) -> np.ndarray:
    """Convert unit quaternions to 3x3 rotation matrices.

    Args:
        q: Unit quaternions with shape ``(..., 4)``.

    Returns:
        Rotation matrices with shape ``(..., 3, 3)``.
    """
    q = quat_normalize(q)
    w, x, y, z = q[..., 0], q[..., 1], q[..., 2], q[..., 3]
    xx, yy, zz = x * x, y * y, z * z
    xy, xz, yz = x * y, x * z, y * z
    wx, wy, wz = w * x, w * y, w * z

    return np.stack(
        [
            np.stack([1.0 - 2.0 * (yy + zz), 2.0 * (xy - wz), 2.0 * (xz + wy)], axis=-1),
            np.stack([2.0 * (xy + wz), 1.0 - 2.0 * (xx + zz), 2.0 * (yz - wx)], axis=-1),
            np.stack([2.0 * (xz - wy), 2.0 * (yz + wx), 1.0 - 2.0 * (xx + yy)], axis=-1),
        ],
        axis=-2,
    )


# Axis letter to index. Blender applies an order like "XYZ" as X first, then Y,
# then Z, so the matrix is ``R_k @ R_j @ R_i``.
_AXIS_INDEX = {"X": 0, "Y": 1, "Z": 2}
_EULER_ORDERS = ("XYZ", "XZY", "YXZ", "YZX", "ZXY", "ZYX")


def matrix_to_euler(m: np.ndarray, order: str = "XYZ") -> np.ndarray:
    """Extract Euler angles from 3x3 rotation matrices, matching Blender.

    Every rotation has two Euler representations. Blender returns whichever has
    the smaller total absolute angle, and this reproduces that choice so the
    values match ``mathutils.Quaternion.to_euler``.

    Args:
        m: Rotation matrices with shape ``(..., 3, 3)``.
        order: One of the six Tait-Bryan orders Blender supports.

    Returns:
        Angles with shape ``(..., 3)`` ordered ``(x, y, z)``.

    Raises:
        ValueError: If ``order`` is not a supported rotation order.
    """
    if order not in _EULER_ORDERS:
        raise ValueError(f"Unsupported rotation order: {order!r}")

    m = np.asarray(m, dtype=np.float64)
    i = _AXIS_INDEX[order[0]]
    j = _AXIS_INDEX[order[1]]
    k = _AXIS_INDEX[order[2]]
    # +1 for the cyclic orders (XYZ, YZX, ZXY), -1 for the rest.
    parity = 1.0 if (j - i) % 3 == 1 else -1.0

    sin_j = np.clip(-parity * m[..., k, i], -1.0, 1.0)
    cos_j = np.sqrt(np.clip(1.0 - sin_j * sin_j, 0.0, 1.0))

    numerator_i = parity * m[..., k, j]
    denominator_i = m[..., k, k]
    numerator_k = parity * m[..., j, i]
    denominator_k = m[..., i, i]

    first = np.stack(
        [
            np.arctan2(numerator_i, denominator_i),
            np.arctan2(sin_j, cos_j),
            np.arctan2(numerator_k, denominator_k),
        ],
        axis=-1,
    )
    second = np.stack(
        [
            np.arctan2(-numerator_i, -denominator_i),
            np.arctan2(sin_j, -cos_j),
            np.arctan2(-numerator_k, -denominator_k),
        ],
        axis=-1,
    )

    # At gimbal lock the first and last angles are no longer separable, so all of
    # the rotation is folded into the first one.
    gimbal = cos_j < 1e-7
    locked = np.stack(
        [
            np.arctan2(-parity * m[..., j, k], m[..., j, j]),
            np.arctan2(sin_j, cos_j),
            np.zeros_like(sin_j),
        ],
        axis=-1,
    )

    use_second = np.sum(np.abs(second), axis=-1) < np.sum(np.abs(first), axis=-1)
    chosen = np.where(use_second[..., None], second, first)
    chosen = np.where(gimbal[..., None], locked, chosen)

    out = np.empty((*m.shape[:-2], 3), dtype=np.float64)
    out[..., i] = chosen[..., 0]
    out[..., j] = chosen[..., 1]
    out[..., k] = chosen[..., 2]
    return out


def ensure_continuity(quats: np.ndarray) -> np.ndarray:
    """Flip quaternion signs so consecutive frames stay on the same hemisphere.

    Prevents interpolation artifacts once the values are written to FCurves.
    Operates along axis 0, which is the frame axis.

    Args:
        quats: Quaternion tracks with shape ``(frames, ..., 4)``.

    Returns:
        A sign-corrected copy with the same shape.
    """
    quats = np.array(quats, dtype=np.float64, copy=True)
    for frame in range(1, quats.shape[0]):
        dot = np.sum(quats[frame] * quats[frame - 1], axis=-1, keepdims=True)
        quats[frame] = np.where(dot < 0.0, -quats[frame], quats[frame])
    return quats


def transform_inverse(rotation: np.ndarray, translation: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Invert rigid transforms expressed as a quaternion and a translation.

    Args:
        rotation: Unit quaternions with shape ``(..., 4)``.
        translation: Translations with shape ``(..., 3)``.

    Returns:
        Tuple of inverted ``(rotation, translation)``.
    """
    inverse_rotation = quat_conjugate(rotation)
    return inverse_rotation, -quat_rotate_vector(inverse_rotation, translation)


def transform_multiply(
    rotation_a: np.ndarray,
    translation_a: np.ndarray,
    rotation_b: np.ndarray,
    translation_b: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Compose two rigid transforms, applying ``b`` first and then ``a``.

    Args:
        rotation_a: Unit quaternions broadcastable to ``(..., 4)``.
        translation_a: Translations broadcastable to ``(..., 3)``.
        rotation_b: Unit quaternions broadcastable to ``(..., 4)``.
        translation_b: Translations broadcastable to ``(..., 3)``.

    Returns:
        Tuple of the composed ``(rotation, translation)``.
    """
    rotation = quat_multiply(rotation_a, rotation_b)
    translation = translation_a + quat_rotate_vector(rotation_a, translation_b)
    return rotation, translation


def decompose_matrix(matrix: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Split 4x4 column-vector matrices into a rotation quaternion and translation.

    Scale is stripped by normalizing the basis columns.

    Args:
        matrix: Matrices with shape ``(..., 4, 4)``.

    Returns:
        Tuple of w-first quaternion ``(..., 4)`` and translation ``(..., 3)``.
    """
    matrix = np.asarray(matrix, dtype=np.float64)
    translation = matrix[..., :3, 3]
    basis = matrix[..., :3, :3]
    norms = np.linalg.norm(basis, axis=-2, keepdims=True)
    basis = basis / np.where(norms > _EPSILON, norms, 1.0)
    return quat_from_matrix(basis), translation
