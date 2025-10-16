package com.da.extractor.service;

import co.elastic.clients.elasticsearch.ElasticsearchClient;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;
import co.elastic.clients.elasticsearch.core.SearchRequest;
import co.elastic.clients.elasticsearch.core.SearchResponse;
import co.elastic.clients.elasticsearch.core.search.Hit;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.lang.reflect.Type;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;

/**
 * Extractor - Componente responsable de extraer datos de Elasticsearch.
 *
 * Funcionalidades principales:
 * - Conexión y consulta a Elasticsearch
 * - Ejecución de queries DSL configurables
 * - Manejo de ventanas de tiempo dinámicas
 * - Extracción de logs y agregaciones
 * - Conversión de resultados a formato procesable
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class ElasticsearchExtractor {

    private final ElasticsearchClient elasticsearchClient;
    private final ObjectMapper objectMapper;

    /**
     * Extrae datos de Elasticsearch basado en una consulta configurada.
     *
     * @param index Índice de Elasticsearch donde buscar
     * @param queryMap Consulta DSL en formato Map
     * @param timeWindow Ventana de tiempo (ej: "1h", "1d", "1M")
     * @return Lista de documentos extraídos
     */
    public List<Map<String, Object>> extractData(String index, Map<String, Object> queryMap, String timeWindow) {
        log.info("Extrayendo datos del índice '{}' con ventana de tiempo '{}'", index, timeWindow);

        try {
            // Preparar la consulta con filtro de tiempo
            Map<String, Object> enhancedQuery = enhanceQueryWithTimeFilter(queryMap, timeWindow);

            // Convertir el Map a Query de Elasticsearch
            Query query = buildElasticsearchQuery(enhancedQuery);

            // Construir y ejecutar la búsqueda
            SearchRequest searchRequest = SearchRequest.of(s -> s
                .index(index)
                .query(query)
                .size(10000) // Máximo de documentos a extraer por consulta
            );

            SearchResponse<Map<String, Object>> response = elasticsearchClient.search(searchRequest, (Type) Map.class);

            // Extraer los documentos de la respuesta
            List<Map<String, Object>> documents = response.hits().hits().stream()
                .map(Hit::source)
                .map(this::convertToStringObjectMap)
                .toList();

            log.info("Extraídos {} documentos del índice '{}'", documents.size(), index);
            return documents;

        } catch (Exception e) {
            log.error("Error extrayendo datos de Elasticsearch: {}", e.getMessage(), e);
            throw new RuntimeException("Falló la extracción de datos de Elasticsearch", e);
        }
    }

    /**
     * Mejora la consulta agregando filtros de tiempo basados en la ventana especificada.
     */
    private Map<String, Object> enhanceQueryWithTimeFilter(Map<String, Object> originalQuery, String timeWindow) {
        // Calcular timestamp de inicio basado en la ventana de tiempo
        LocalDateTime endTime = LocalDateTime.now();
        LocalDateTime startTime = calculateStartTime(endTime, timeWindow);

        log.debug("Aplicando filtro de tiempo: {} a {}", startTime, endTime);

        // Crear filtro de rango temporal
        Map<String, Object> timeFilter = Map.of(
            "range", Map.of(
                "@timestamp", Map.of(
                    "gte", startTime.toInstant(ZoneOffset.UTC).toEpochMilli(),
                    "lte", endTime.toInstant(ZoneOffset.UTC).toEpochMilli()
                )
            )
        );

        // Si la consulta original está vacía, usar solo el filtro de tiempo
        if (originalQuery == null || originalQuery.isEmpty()) {
            return Map.of("bool", Map.of("filter", List.of(timeFilter)));
        }

        // Combinar consulta original con filtro de tiempo
        return Map.of(
            "bool", Map.of(
                "must", List.of(originalQuery),
                "filter", List.of(timeFilter)
            )
        );
    }

    /**
     * Calcula el tiempo de inicio basado en la ventana de tiempo especificada.
     */
    private LocalDateTime calculateStartTime(LocalDateTime endTime, String timeWindow) {
        if (timeWindow == null || timeWindow.isEmpty()) {
            return endTime.minusHours(1); // Por defecto: última hora
        }

        String unit = timeWindow.substring(timeWindow.length() - 1).toLowerCase();
        int value = Integer.parseInt(timeWindow.substring(0, timeWindow.length() - 1));

        return switch (unit) {
            case "m" -> endTime.minusMinutes(value);
            case "h" -> endTime.minusHours(value);
            case "d" -> endTime.minusDays(value);
            case "w" -> endTime.minusWeeks(value);
            case "M", "mo" -> endTime.minusMonths(value);
            default -> {
                log.warn("Formato de ventana de tiempo no reconocido: {}. Usando 1 hora por defecto.", timeWindow);
                yield endTime.minusHours(1);
            }
        };
    }

    /**
     * Construye una Query de Elasticsearch a partir de un Map.
     */
    private Query buildElasticsearchQuery(Map<String, Object> queryMap) {
        try {
            String queryJson = objectMapper.writeValueAsString(queryMap);
            return Query.of(q -> q.withJson(new java.io.ByteArrayInputStream(queryJson.getBytes())));
        } catch (Exception e) {
            log.error("Error construyendo query de Elasticsearch: {}", e.getMessage(), e);
            throw new RuntimeException("Error en la construcción de la consulta", e);
        }
    }

    /**
     * Convierte Map<String, Object> para asegurar compatibilidad de tipos.
     */
    private Map<String, Object> convertToStringObjectMap(Map<String, Object> source) {
        return source;
    }
}
