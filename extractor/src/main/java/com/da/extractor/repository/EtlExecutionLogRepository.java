package com.da.extractor.repository;

import com.da.extractor.model.EtlExecutionLog;
import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.stereotype.Repository;

import java.time.LocalDateTime;
import java.util.List;

/**
 * Repositorio para acceder a los logs de ejecución ETL almacenados en MongoDB.
 *
 * Funcionalidades:
 * - Almacenamiento de metadatos de ejecución
 * - Consulta de historial de ejecuciones por job
 * - Filtrado por estado y fechas para monitoreo
 */
@Repository
public interface EtlExecutionLogRepository extends MongoRepository<EtlExecutionLog, String> {

    /**
     * Encuentra logs de ejecución por ID de job
     * @param jobId ID del job ETL
     * @return Lista de logs ordenados por fecha descendente
     */
    List<EtlExecutionLog> findByJobIdOrderByStartTimeDesc(String jobId);

    /**
     * Encuentra logs por estado de ejecución
     * @param status Estado de la ejecución (SUCCESS, ERROR, RUNNING)
     * @return Lista de logs con el estado especificado
     */
    List<EtlExecutionLog> findByStatus(String status);

    /**
     * Encuentra logs en un rango de fechas
     * @param start Fecha de inicio
     * @param end Fecha de fin
     * @return Lista de logs en el rango especificado
     */
    List<EtlExecutionLog> findByStartTimeBetween(LocalDateTime start, LocalDateTime end);

    /**
     * Encuentra el último log de ejecución de un job específico
     * @param jobId ID del job ETL
     * @return Último log de ejecución o null
     */
    EtlExecutionLog findFirstByJobIdOrderByStartTimeDesc(String jobId);
}
