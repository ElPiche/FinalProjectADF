package com.da.extractor.service;

import com.da.extractor.model.EtlExecutionLog;
import com.da.extractor.repository.EtlExecutionLogRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

/**
 * Loader - Componente responsable de cargar datos transformados en MongoDB.
 *
 * Funcionalidades principales:
 * - Inserción de datos procesados en colecciones de destino
 * - Actualización de registros existentes (upsert)
 * - Registro de metadatos de ejecución para auditoría
 * - Manejo de errores durante la carga
 * - Logging detallado para monitoreo
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class DataLoader {

    @Qualifier("targetMongoTemplate")
    private final MongoTemplate targetMongoTemplate;

    private final EtlExecutionLogRepository executionLogRepository;

    /**
     * Carga datos transformados en la colección de destino especificada.
     *
     * @param data Datos transformados listos para cargar
     * @param targetCollection Nombre de la colección de destino
     * @param jobId ID del job ETL que está ejecutándose
     * @param jobName Nombre del job ETL
     * @return Número de registros cargados exitosamente
     */
    public long loadData(List<Map<String, Object>> data, String targetCollection, String jobId, String jobName) {
        log.info("Iniciando carga de {} registros en colección '{}'", data.size(), targetCollection);

        if (data == null || data.isEmpty()) {
            log.warn("No hay datos para cargar en la colección '{}'", targetCollection);
            return 0;
        }

        long startTime = System.currentTimeMillis();
        long loadedCount = 0;

        try {
            // Preparar metadatos de carga
            LocalDateTime loadTimestamp = LocalDateTime.now();

            // Agregar metadatos a cada documento
            data.forEach(document -> {
                document.put("loaded_at", loadTimestamp);
                document.put("job_id", jobId);
                document.put("job_name", jobName);
            });

            // Insertar datos en la colección de destino
            targetMongoTemplate.insert(data, targetCollection);
            loadedCount = data.size();

            long duration = System.currentTimeMillis() - startTime;
            log.info("Carga completada: {} registros insertados en '{}' en {} ms",
                    loadedCount, targetCollection, duration);

            // Registrar éxito en log de ejecución
            logSuccessfulLoad(jobId, jobName, data.size(), loadedCount, duration);

            return loadedCount;

        } catch (Exception e) {
            long duration = System.currentTimeMillis() - startTime;
            log.error("Error durante la carga de datos en '{}': {}", targetCollection, e.getMessage(), e);

            // Registrar error en log de ejecución
            logFailedLoad(jobId, jobName, data.size(), e.getMessage(), duration);

            throw new RuntimeException("Falló la carga de datos en MongoDB", e);
        }
    }

    /**
     * Carga datos con operación upsert para evitar duplicados.
     *
     * @param data Datos transformados listos para cargar
     * @param targetCollection Nombre de la colección de destino
     * @param jobId ID del job ETL que está ejecutándose
     * @param jobName Nombre del job ETL
     * @param keyField Campo que se usa como clave única para upsert
     * @return Número de registros procesados
     */
    public long upsertData(List<Map<String, Object>> data, String targetCollection,
                          String jobId, String jobName, String keyField) {
        log.info("Iniciando upsert de {} registros en colección '{}' usando clave '{}'",
                data.size(), targetCollection, keyField);

        if (data == null || data.isEmpty()) {
            log.warn("No hay datos para hacer upsert en la colección '{}'", targetCollection);
            return 0;
        }

        long startTime = System.currentTimeMillis();
        long processedCount = 0;

        try {
            LocalDateTime loadTimestamp = LocalDateTime.now();

            for (Map<String, Object> document : data) {
                // Agregar metadatos
                document.put("updated_at", loadTimestamp);
                document.put("job_id", jobId);
                document.put("job_name", jobName);

                // Realizar upsert basado en el campo clave
                Object keyValue = document.get(keyField);
                if (keyValue != null) {
                    org.springframework.data.mongodb.core.query.Query query =
                        org.springframework.data.mongodb.core.query.Query.query(
                            org.springframework.data.mongodb.core.query.Criteria.where(keyField).is(keyValue)
                        );

                    org.springframework.data.mongodb.core.query.Update update =
                        new org.springframework.data.mongodb.core.query.Update();

                    // Agregar todos los campos del documento al update
                    document.forEach(update::set);

                    targetMongoTemplate.upsert(query, update, targetCollection);
                    processedCount++;
                } else {
                    log.warn("Documento sin clave '{}', insertando directamente", keyField);
                    targetMongoTemplate.insert(document, targetCollection);
                    processedCount++;
                }
            }

            long duration = System.currentTimeMillis() - startTime;
            log.info("Upsert completado: {} registros procesados en '{}' en {} ms",
                    processedCount, targetCollection, duration);

            // Registrar éxito en log de ejecución
            logSuccessfulLoad(jobId, jobName, data.size(), processedCount, duration);

            return processedCount;

        } catch (Exception e) {
            long duration = System.currentTimeMillis() - startTime;
            log.error("Error durante upsert en '{}': {}", targetCollection, e.getMessage(), e);

            // Registrar error en log de ejecución
            logFailedLoad(jobId, jobName, data.size(), e.getMessage(), duration);

            throw new RuntimeException("Falló el upsert de datos en MongoDB", e);
        }
    }

    /**
     * Registra una carga exitosa en el log de ejecución.
     */
    private void logSuccessfulLoad(String jobId, String jobName, long recordsToLoad,
                                  long recordsLoaded, long durationMs) {
        try {
            EtlExecutionLog log = new EtlExecutionLog();
            log.setJobId(jobId);
            log.setJobName(jobName);
            log.setStartTime(LocalDateTime.now().minusNanos(durationMs * 1_000_000));
            log.setEndTime(LocalDateTime.now());
            log.setDurationMs(durationMs);
            log.setStatus("SUCCESS");
            log.setRecordsProcessed((long) recordsToLoad);
            log.setRecordsLoaded(recordsLoaded);

            executionLogRepository.save(log);

        } catch (Exception e) {
            log.error("Error guardando log de ejecución exitosa: {}", e.getMessage(), e);
        }
    }

    /**
     * Registra una carga fallida en el log de ejecución.
     */
    private void logFailedLoad(String jobId, String jobName, long recordsToLoad,
                              String errorMessage, long durationMs) {
        try {
            EtlExecutionLog log = new EtlExecutionLog();
            log.setJobId(jobId);
            log.setJobName(jobName);
            log.setStartTime(LocalDateTime.now().minusNanos(durationMs * 1_000_000));
            log.setEndTime(LocalDateTime.now());
            log.setDurationMs(durationMs);
            log.setStatus("ERROR");
            log.setRecordsProcessed((long) recordsToLoad);
            log.setRecordsLoaded(0L);
            log.setErrorMessage(errorMessage);

            executionLogRepository.save(log);

        } catch (Exception e) {
            log.error("Error guardando log de ejecución fallida: {}", e.getMessage(), e);
        }
    }

    /**
     * Obtiene estadísticas de la colección de destino.
     *
     * @param targetCollection Nombre de la colección
     * @return Mapa con estadísticas básicas
     */
    public Map<String, Object> getCollectionStats(String targetCollection) {
        try {
            long documentCount = targetMongoTemplate.getCollection(targetCollection).countDocuments();

            return Map.of(
                "collection", targetCollection,
                "document_count", documentCount,
                "checked_at", LocalDateTime.now()
            );

        } catch (Exception e) {
            log.error("Error obteniendo estadísticas de colección '{}': {}", targetCollection, e.getMessage());
            return Map.of(
                "collection", targetCollection,
                "error", e.getMessage(),
                "checked_at", LocalDateTime.now()
            );
        }
    }
}
