package strutils

import (
	"encoding/json"
	"reflect"
)

func JSONStringsEqual(a, b []byte) (bool, error) {
	var dataA, dataB any
	err := json.Unmarshal(a, &dataA)
	if err != nil {
		return false, err
	}

	err = json.Unmarshal(b, &dataB)
	if err != nil {
		return false, err
	}

	return reflect.DeepEqual(dataA, dataB), nil
}
