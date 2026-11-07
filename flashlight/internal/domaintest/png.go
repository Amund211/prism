package domaintest

import (
	"bytes"
	"encoding/binary"
	"hash/crc32"
)

// NewPNG builds a PNG signature and IHDR chunk followed by filler zero bytes.
// Only the header is checked on upload, so the rest need not be image data.
func NewPNG(width, height uint32, bitDepth, colorType byte, filler int) []byte {
	var buf bytes.Buffer
	buf.Write([]byte("\x89PNG\r\n\x1a\n"))
	ihdr := make([]byte, 13)
	binary.BigEndian.PutUint32(ihdr[0:4], width)
	binary.BigEndian.PutUint32(ihdr[4:8], height)
	ihdr[8] = bitDepth
	ihdr[9] = colorType
	_ = binary.Write(&buf, binary.BigEndian, uint32(13))
	chunk := append([]byte("IHDR"), ihdr...)
	buf.Write(chunk)
	_ = binary.Write(&buf, binary.BigEndian, crc32.ChecksumIEEE(chunk))
	buf.Write(bytes.Repeat([]byte{0}, filler))
	return buf.Bytes()
}
