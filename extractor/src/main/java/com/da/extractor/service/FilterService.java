package com.da.extractor.service;

import com.da.extractor.entity.Serie;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

@Service
public class FilterService {

    /// Recibe un Map que representa la respusta de una consulta Elasticsearch y lo trasforma a una Serie filtrada
    /// @param data El Map con los datos de la consulta Elasticsearch
    /// @return Un objeto Serie con los datos filtrados
    public Serie applyFilter(Map<String, Object> data, String kbId, String description) {

        if(data.containsKey("error")){
            throw new IllegalArgumentException(
                    "No se puede aplica filtro ya que la data contiene un error: " + data.get("error"));
        }

        if(!data.containsKey("columns") || !data.containsKey("values")){
            throw  new IllegalArgumentException("Data inválida: faltan las claves 'columns' o 'values'");
        }

        List<Map> columns = (List<Map>) data.get("columns");
        List<List> values = (List<List>) data.get("values");

        // Crear lista unificada
        List<Map<String, Object>> unifiedData = new ArrayList<>();

        for (List row : values) {
            Map<String, Object> rowMap = new HashMap<>();
            for (int i = 0; i < columns.size(); i++) {
                String columnName = (String) ((Map<?, ?>) columns.get(i)).get("name");
                Object value = row.get(i);
                rowMap.put(columnName, value);
            }
            unifiedData.add(rowMap);
        }


        return new Serie(null, kbId, description, unifiedData);
    }

}
